"""
任务队列消费模块 — 串行处理消息 pipeline，调度失败重试。
所有外部调用失败均降级处理，只有 Typecho 发布失败才进入重试队列。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from datetime import datetime, timedelta, timezone

from . import filter as filter_mod
from . import parse as parse_mod
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
            logger.info("🔁 待重试记录 | 数量=%d", len(due))
        for record in due:
            raw = _latest_raw_msg(conn, record["hash_key"])
            if not raw:
                continue
            await queue.put(RawMessage(
                channel=raw["channel"],
                msg_id=raw["msg_id"],
                msg_date=raw["msg_date"] or "",
                text=raw["raw_text"],
                is_edit=False,
                message=None,   # 重试不重新下载图片
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
    # 1. 消息级去重（编辑消息不跳过，需要更新文章）
    if not msg.is_edit and repo.msg_exists(conn, msg.channel, msg.msg_id):
        logger.debug("⏭️  已处理跳过 | channel=%s msg_id=%d", msg.channel, msg.msg_id)
        return

    # 2. 广告过滤
    if filter_mod.should_block(msg.text):
        logger.info("🚫 广告过滤 | channel=%s msg_id=%d", msg.channel, msg.msg_id)
        repo.save_msg(conn, msg.channel, msg.msg_id, msg.msg_date, msg.text, "", is_ad=True)
        return

    # 3. 文本清洗（去除推广行、网盘链接、尾部导流）+ 解析
    clean = filter_mod.clean_text(msg.text)
    parsed = parse_mod.parse(clean)
    if not parsed:
        logger.warning("⚠️  解析失败跳过 | msg_id=%d", msg.msg_id)
        return
    logger.debug("🔍 解析完成 | 片名=%s EP=%s", parsed.name, parsed.episode_raw)

    # 4. 保存消息记录（存原始文本，便于排查）
    repo.save_msg(conn, msg.channel, msg.msg_id, msg.msg_date,
                  msg.text, parsed.hash_key, dataclasses.asdict(parsed))

    # 5. 查历史发布记录
    existing = repo.get_post(conn, parsed.hash_key)

    # 6. 图片处理（可降级）
    image_urls, img_hash_val = await _handle_images(msg, existing, tg_client, cfg)

    # 7. TMDB 查询（带缓存，可降级）
    tmdb_result = await _get_tmdb_cached(conn, parsed, cfg)

    # 8. 融合 + 渲染
    merged = merge_mod.merge(parsed, tmdb_result, image_urls)
    post = render_mod.render(merged)

    # 9. content_hash 检查
    c_hash = content_hash(merged.episode_num, merged.extra_quality, merged.size_per_ep)
    cid = existing.get("typecho_cid") if existing else None
    if cid and existing.get("content_hash") == c_hash:
        logger.debug("⏭️  内容无变化跳过 | hash_key=%s", parsed.hash_key)
        return

    # 10. 发布到 Typecho
    retry_count = (existing or {}).get("retry_count", 0)
    try:
        if cid:
            await publish_client.edit_post(
                cid, post.title, post.content, post.slug, post.category, post.tags
            )
            url = (existing or {}).get("typecho_url", "")
            logger.info("🔄 更新成功 | 《%s》%s cid=%d", merged.name, merged.episode_raw, cid)
        else:
            cid = await publish_client.new_post(
                post.title, post.content, post.slug, post.category, post.tags
            )
            base = cfg.typecho_xmlrpc_endpoint.rsplit("/action", 1)[0]
            url = f"{base}/{post.slug}.html"
            logger.info("✅ 发布成功 | 《%s》%s cid=%d", merged.name, merged.episode_raw, cid)

        repo.save_post(
            conn, parsed.hash_key, cid, url, post.title,
            merged.episode_num, c_hash, merged.cover_image_url,
            merged.extra_image_urls, img_hash_val,
            dataclasses.asdict(tmdb_result) if tmdb_result else None,
        )
        await notify.send_success(merged.name, merged.episode_raw, url, cfg)

    except PublishError as e:
        await _handle_failure(conn, parsed.hash_key, merged.name, str(e), retry_count, cfg)


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
