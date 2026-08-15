"""
任务队列消费模块 — 串行处理消息 pipeline，调度失败重试。
所有外部调用失败均降级处理，只有 Typecho 发布失败才进入重试队列。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from . import filter as filter_mod
from . import parse as parse_mod
from . import ai_parse as ai_parse_mod
from . import fetch as fetch_mod
from . import imgbed as imgbed_mod
from . import tmdb as tmdb_mod
from . import merge as merge_mod
from . import render as render_mod
from . import repo
from . import notify
from .config import Config
from .listen import RawMessage
from .publish import TypechoClient, PublishError
from .utils import content_hash, now_iso

logger = logging.getLogger(__name__)

# 慢操作阈值（秒）
_SLOW_DEDUP_SEC = 0.1
_SLOW_PUBLISH_SEC = 2.0


async def run(
    queue: asyncio.Queue,
    publish_client: TypechoClient,
    tg_client: object,
    conn: object,
    cfg: Config,
) -> None:
    """串行消费队列，异常不中断循环"""
    while True:
        msg: RawMessage = await queue.get()
        try:
            await _process(msg, publish_client, tg_client, conn, cfg)
        except Exception as e:
            logger.exception("pipeline 未预期异常 | msg_id=%s error=%s", msg.msg_id, e)
        finally:
            queue.task_done()


async def retry_loop(
    queue: asyncio.Queue, conn: object, cfg: Config
) -> None:
    """每5分钟扫描到期失败记录，重新入队（重试时 message=None，跳过图片下载）"""
    while True:
        await asyncio.sleep(300)
        due = repo.get_retry_due(conn, now_iso(), cfg.retry_max)
        if due:
            # 打印积压总量：本轮数量受 LIMIT 限制，只有总量能反映积压是否在收敛。
            # 若总量长时间不降，说明重试没有真正执行（历史上曾因消息级去重空转）。
            logger.info("🔁 待重试记录 | 本轮=%d 积压=%d",
                        len(due), repo.count_retry_pending(conn, cfg.retry_max))
        for record in due:
            raw = _latest_raw_msg(conn, record["hash_key"])
            if not raw:
                # tg_messages 里找不到原始消息，重试无从下手。必须标记 dead，
                # 否则该记录会一直满足 get_retry_due 条件，每轮都被无效回捞。
                repo.mark_dead(conn, record["hash_key"], "重试失败：tg_messages 中无对应原始消息")
                logger.error("💀 无法重试 | hash_key=%s 原始消息已丢失，标记 dead", record["hash_key"])
                continue
            await queue.put(RawMessage(
                channel=raw["channel"],
                msg_id=raw["msg_id"],
                msg_date=raw["msg_date"] or "",
                text=raw["raw_text"],
                is_edit=False,
                message=None,   # 重试不重新下载图片
                is_retry=True,  # 豁免消息级去重，否则重试会被当作"已处理"跳过
            ))


def _latest_raw_msg(conn: object, hash_key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM tg_messages WHERE hash_key=? ORDER BY msg_id DESC LIMIT 1",
        (hash_key,),
    ).fetchone()
    return dict(row) if row else None


# ── pipeline ──────────────────────────────────────────────────────────────────

async def _process(
    msg: RawMessage,
    publish_client: TypechoClient,
    tg_client: object,
    conn: object,
    cfg: Config,
) -> None:
    # 1. 消息级去重（编辑消息和重试不跳过：前者需要更新文章，后者需要重发）
    if not msg.is_edit and not msg.is_retry and repo.msg_exists(conn, msg.channel, msg.msg_id):
        logger.debug("⏭️  已处理跳过 | [%s] msg_id=%d", msg.channel_title or msg.channel, msg.msg_id)
        return

    # 2. 广告过滤
    if block_reason := filter_mod.should_block(msg.text):
        ch = msg.channel_title or msg.channel
        logger.info("🚫 广告过滤 | [%s] msg_id=%d 原因=%s", ch, msg.msg_id, block_reason)
        repo.save_msg(conn, msg.channel, msg.msg_id, msg.msg_date, msg.text, "", is_ad=True)
        await notify.send_blocked(block_reason, cfg)
        return

    # 3. 文本清洗（去除推广行、网盘链接、尾部导流）
    clean = filter_mod.clean_text(msg.text)

    # 4. 解析（AI 优先，失败自动降级正则）
    parsed = None
    if cfg.ai_parse_enable:
        try:
            parsed = await ai_parse_mod.parse(clean, cfg)
        except Exception as e:
            logger.warning("🤖 AI 解析异常，降级正则 | msg_id=%d error=%s", msg.msg_id, e)
    if parsed is None:
        parsed = parse_mod.parse(clean)

    if not parsed:
        logger.warning("⚠️  解析失败跳过 | [%s] msg_id=%d", msg.channel_title or msg.channel, msg.msg_id)
        return
    logger.debug("🔍 解析完成 | 片名=%s EP=%s", parsed.name, parsed.episode_raw)

    # 5. 查历史发布记录。双向匹配 hash_key / alt_hash_key：AI 与正则是两套独立的
    #    片名+年份提取器，AI 偶发失败降级后 key 会变，只按主键查会判定"没有历史
    #    记录"从而重复建文（这正是 typecho_contents 大量 INSERT 的来源）。
    dedup_started = time.monotonic()
    hash_key = parsed.hash_key
    existing = repo.find_post(conn, hash_key, parsed.alt_hash_key)
    if existing is not None and existing["hash_key"] != hash_key:
        # 命中的是另一条路径建立的记录 → 沿用它的 key，后续 save_post 更新同一行、
        # 复用同一个 typecho_cid，走 editPost 而不是 newPost。
        logger.info("🔗 去重键兜底命中 | 本次=%s 复用历史=%s",
                    hash_key, existing["hash_key"])
        hash_key = existing["hash_key"]
    cid = existing.get("typecho_cid") if existing else None
    dedup_ms = (time.monotonic() - dedup_started) * 1000
    logger.info("[DEDUP] key=%s found=%s cid=%s elapsed=%.1fms",
                hash_key, existing is not None, cid, dedup_ms)
    if dedup_ms > _SLOW_DEDUP_SEC * 1000:
        logger.warning("[SLOW_DEDUP] key=%s elapsed=%.0fms", hash_key, dedup_ms)

    # 6. 保存消息记录（存原始文本，便于排查）。落库用解析出的最终 key，
    #    保证 retry_loop 按 hash_key 回捞原始消息时能找到。
    repo.save_msg(conn, msg.channel, msg.msg_id, msg.msg_date,
                  msg.text, hash_key, dataclasses.asdict(parsed))

    # 7. content_hash 检查 —— 提前到所有网络调用之前。
    #    merge 对这三个字段是原样透传（见 merge.py），此处算出的指纹与融合后
    #    完全一致；内容没变时可以直接跳过图片下载/上传和 TMDB 查询。
    c_hash = content_hash(parsed.episode_num, parsed.extra_quality, parsed.size_per_ep)
    if cid and existing.get("content_hash") == c_hash:
        logger.debug("⏭️  内容无变化跳过 | hash_key=%s", hash_key)
        return

    # 8. 图片处理（可降级）
    image_urls, img_hash_val = await _handle_images(msg, existing, tg_client, cfg)

    # 9. TMDB 查询（带缓存，可降级；短剧/音乐等跳过）
    tmdb_result = None
    if not parsed.skip_tmdb:
        tmdb_result = await _get_tmdb_cached(conn, parsed, cfg)

    # 10. 融合 + 渲染
    merged = merge_mod.merge(parsed, tmdb_result, image_urls)
    post = render_mod.render(merged)

    # 11. 发布到 Typecho
    retry_count = (existing or {}).get("retry_count", 0)
    publish_started = time.monotonic()
    try:
        if cid:
            await publish_client.edit_post(
                cid, post.title, post.content, post.slug,
                post.category, post.tags, post.excerpt,
            )
            action = "update"
            url = (existing or {}).get("typecho_url", "")
            logger.info("🔄 更新成功 | [%s] 《%s》%s cid=%d",
                        msg.channel_title or msg.channel, merged.name, merged.episode_raw, cid)
        else:
            cid = await publish_client.new_post(
                post.title, post.content, post.slug,
                post.category, post.tags, post.excerpt,
            )
            action = "create"
            base = cfg.typecho_xmlrpc_endpoint.rsplit("/action", 1)[0]
            url = f"{base}/archives/{post.slug}.html"
            logger.info("✅ 发布成功 | [%s] 《%s》%s cid=%d",
                        msg.channel_title or msg.channel, merged.name, merged.episode_raw, cid)

        publish_ms = (time.monotonic() - publish_started) * 1000
        logger.info("[PUBLISH] action=%s key=%s cid=%s cat=%s tags=%d elapsed=%.0fms",
                    action, hash_key, cid, post.category, len(post.tags), publish_ms)
        if publish_ms > _SLOW_PUBLISH_SEC * 1000:
            logger.warning("[SLOW_PUBLISH] action=%s key=%s elapsed=%.0fms",
                           action, hash_key, publish_ms)

        # 记录"另一条解析路径算出的 key"作为别名：hash_key 被兜底改写时，别名是
        # 本次自己算出的 key；否则是本次的备用键。两种情况都让下次任一路径直接命中。
        alias = parsed.hash_key if hash_key != parsed.hash_key else parsed.alt_hash_key
        repo.save_post(
            conn, hash_key, cid, url, post.title,
            merged.episode_num, c_hash, merged.cover_image_url,
            merged.extra_image_urls, img_hash_val,
            dataclasses.asdict(tmdb_result) if tmdb_result else None,
            alias,
        )
        await notify.send_success(merged.name, merged.episode_raw, url, cfg)

    except PublishError as e:
        logger.warning("[ERROR] stage=publish key=%s error=%s", hash_key, e)
        await _handle_failure(conn, hash_key, merged.name, str(e), retry_count, cfg)


async def _handle_images(
    msg: RawMessage, existing: dict | None, tg_client: object, cfg: Config
) -> tuple[list[str], str]:
    """图片下载 → 上传，失败降级；重试模式（message=None）直接复用历史URL"""
    stored_urls = (
        ([existing["cover_image_url"]] if existing and existing.get("cover_image_url") else []) +
        json.loads((existing or {}).get("extra_image_urls") or "[]")
    )
    stored_hash = (existing or {}).get("tg_img_hash", "")

    if msg.message is None or not cfg.imgbed_enable:
        return stored_urls, stored_hash

    fetched = []
    try:
        fetched = await fetch_mod.download(msg.message, tg_client)
    except Exception as e:
        logger.warning("🖼️  图片下载失败 | error=%s", e)

    if not fetched:
        return stored_urls, stored_hash

    # img_hash 匹配：直接复用历史 URL，不重复上传
    if stored_hash and fetched[0].img_hash == stored_hash:
        logger.debug("♻️  图片复用 | img_hash匹配")
        fetch_mod.cleanup(fetched)
        return stored_urls, stored_hash

    urls: list[str] = []
    try:
        for img in fetched:
            urls.append(await imgbed_mod.upload(img.local_path, cfg))
            logger.debug("☁️  图片上传 | url=%s", urls[-1])
    except Exception as e:
        logger.warning("☁️  图片上传失败 | error=%s", e)
    finally:
        fetch_mod.cleanup(fetched)

    return (urls or stored_urls), (fetched[0].img_hash if fetched else stored_hash)


async def _get_tmdb_cached(conn: object, parsed: object, cfg: Config) -> object:
    """TMDB 查询，自动读写缓存"""
    from .tmdb import TMDBResult
    now = now_iso()
    cached = repo.get_tmdb_cache(conn, parsed.hash_key, now)
    if cached is not None:
        raw = cached.get("tmdb_json")
        return TMDBResult(**json.loads(raw)) if raw else None

    result = await tmdb_mod.search(parsed.name, parsed.year, parsed.is_series, cfg)
    expires = (datetime.now(timezone.utc) + timedelta(days=cfg.tmdb_cache_days)).isoformat()
    repo.save_tmdb_cache(
        conn, parsed.hash_key, parsed.name,
        result.media_type if result else None,
        result.tmdb_id if result else None,
        dataclasses.asdict(result) if result else None,
        result.score if result else 0,
        expires,
    )
    return result


async def _handle_failure(
    conn: object, hash_key: str, name: str,
    error: str, current_retry: int, cfg: Config,
) -> None:
    new_retry = current_retry + 1
    if new_retry >= cfg.retry_max:
        repo.mark_dead(conn, hash_key, error)
        logger.error("💀 彻底放弃 | 《%s》已重试%d次 error=%s", name, cfg.retry_max, error)
        await notify.send_dead(name, error, cfg)
    else:
        next_at = (datetime.now(timezone.utc) + timedelta(minutes=2 ** new_retry)).isoformat()
        repo.mark_failed(conn, hash_key, error, new_retry, next_at)
        logger.error("❌ 发布失败 | 《%s》重试=%d/%d error=%s", name, new_retry, cfg.retry_max, error)
        await notify.send_failure(name, error, new_retry, cfg.retry_max, cfg)
