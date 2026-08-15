"""
数据访问层 — 封装所有 SQLite 读写操作。
上层模块只调用此模块，不直接执行 SQL。
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .utils import now_iso


# ── TG 消息 ───────────────────────────────────────────────────────────────────

def msg_exists(conn: sqlite3.Connection, channel: str, msg_id: int) -> bool:
    """判断该消息是否已处理（去重入口）"""
    row = conn.execute(
        "SELECT 1 FROM tg_messages WHERE channel=? AND msg_id=?",
        (channel, msg_id),
    ).fetchone()
    return row is not None


def save_msg(
    conn: sqlite3.Connection,
    channel: str,
    msg_id: int,
    msg_date: str,
    raw_text: str,
    hash_key: str,
    parsed: dict | None = None,
    is_ad: bool = False,
) -> None:
    """保存 TG 消息记录；若已存在则更新 raw_text 和 parsed（处理编辑消息）"""
    now = now_iso()
    conn.execute(
        """
        INSERT INTO tg_messages (channel, msg_id, msg_date, raw_text, parsed_json, hash_key, is_ad, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel, msg_id) DO UPDATE SET
            raw_text    = excluded.raw_text,
            parsed_json = excluded.parsed_json,
            hash_key    = excluded.hash_key,
            updated_at  = excluded.updated_at
        """,
        (channel, msg_id, msg_date, raw_text,
         json.dumps(parsed, ensure_ascii=False) if parsed else None,
         hash_key, int(is_ad), now),
    )
    conn.commit()


def get_last_msg_id(conn: sqlite3.Connection, channel: str) -> int:
    """返回该频道已处理的最大 msg_id，启动 catch-up 时使用；无记录则返回 0"""
    row = conn.execute(
        "SELECT MAX(msg_id) FROM tg_messages WHERE channel=?", (channel,)
    ).fetchone()
    return row[0] or 0


# ── 发布记录 ──────────────────────────────────────────────────────────────────

def get_post(conn: sqlite3.Connection, hash_key: str) -> dict[str, Any] | None:
    """查询影片的发布记录，不存在返回 None"""
    row = conn.execute(
        "SELECT * FROM content_posts WHERE hash_key=?", (hash_key,)
    ).fetchone()
    return dict(row) if row else None


def find_post(
    conn: sqlite3.Connection, hash_key: str, alt_hash_key: str = ""
) -> dict[str, Any] | None:
    """
    双向查找发布记录，用于抵消 AI / 正则两条解析路径产出的 hash_key 差异。

    AI 与正则是两套独立的片名+年份提取器，同一部影片经常算出不同的 key
    （典型：年份没有括号时正则取不到 year）。AI 偶发失败会让 key 在两个值之间
    来回切换，只按主键查会判定"没有历史记录"从而重复建文。

    查找顺序（全部走唯一索引或 alt 索引，命中即返回）：
      1. hash_key      = 本次 key      —— 常规命中
      2. alt_hash_key  = 本次 key      —— 历史记录由另一条路径创建，本次是它的备用键
      3. hash_key / alt_hash_key = 本次备用键 —— 反向匹配
    """
    row = conn.execute(
        "SELECT * FROM content_posts WHERE hash_key=?", (hash_key,)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM content_posts WHERE alt_hash_key=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (hash_key,),
        ).fetchone()
    if row is None and alt_hash_key:
        row = conn.execute(
            "SELECT * FROM content_posts WHERE hash_key=? OR alt_hash_key=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (alt_hash_key, alt_hash_key),
        ).fetchone()
    return dict(row) if row else None


def save_post(
    conn: sqlite3.Connection,
    hash_key: str,
    cid: int,
    url: str,
    title: str,
    episode_num: int,
    c_hash: str,
    cover_url: str,
    extra_urls: list[str],
    img_hash: str,
    tmdb: dict | None,
    alt_hash_key: str = "",
) -> None:
    """新建或更新发布记录（发布成功时调用）"""
    now = now_iso()
    conn.execute(
        """
        INSERT INTO content_posts
            (hash_key, typecho_cid, typecho_url, last_title, last_episode_num,
             content_hash, cover_image_url, extra_image_urls, tg_img_hash,
             tmdb_json, alt_hash_key, status, retry_count, next_retry_at, error_last,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 0, NULL, NULL, ?, ?)
        ON CONFLICT(hash_key) DO UPDATE SET
            typecho_cid      = excluded.typecho_cid,
            typecho_url      = excluded.typecho_url,
            last_title       = excluded.last_title,
            last_episode_num = excluded.last_episode_num,
            content_hash     = excluded.content_hash,
            cover_image_url  = excluded.cover_image_url,
            extra_image_urls = excluded.extra_image_urls,
            tg_img_hash      = excluded.tg_img_hash,
            tmdb_json        = excluded.tmdb_json,
            -- 本次没有备用键时保留历史值，避免降级路径把已建立的别名抹掉
            alt_hash_key     = COALESCE(NULLIF(excluded.alt_hash_key, ''), content_posts.alt_hash_key),
            status           = 'published',
            retry_count      = 0,
            next_retry_at    = NULL,
            error_last       = NULL,
            updated_at       = excluded.updated_at
        """,
        (hash_key, cid, url, title, episode_num, c_hash, cover_url,
         json.dumps(extra_urls, ensure_ascii=False),
         img_hash,
         json.dumps(tmdb, ensure_ascii=False) if tmdb else None,
         alt_hash_key,
         now, now),
    )
    conn.commit()


def mark_failed(
    conn: sqlite3.Connection,
    hash_key: str,
    error: str,
    retry_count: int,
    next_retry_at: str,
) -> None:
    """标记发布失败，记录重试信息"""
    now = now_iso()
    # 状态：未达到最大重试次数为 failed，否则为 dead（停止自动重试）
    conn.execute(
        """
        INSERT INTO content_posts
            (hash_key, status, retry_count, next_retry_at, error_last, created_at, updated_at)
        VALUES (?, 'failed', ?, ?, ?, ?, ?)
        ON CONFLICT(hash_key) DO UPDATE SET
            status        = excluded.status,
            retry_count   = excluded.retry_count,
            next_retry_at = excluded.next_retry_at,
            error_last    = excluded.error_last,
            updated_at    = excluded.updated_at
        """,
        (hash_key, retry_count, next_retry_at, error[:500], now, now),
    )
    conn.commit()


def mark_dead(conn: sqlite3.Connection, hash_key: str, error: str) -> None:
    """标记为彻底失败（重试耗尽），停止自动重试"""
    now = now_iso()
    conn.execute(
        """
        UPDATE content_posts
        SET status='dead', next_retry_at=NULL, error_last=?, updated_at=?
        WHERE hash_key=?
        """,
        (error[:500], now, hash_key),
    )
    conn.commit()


def mark_settled(conn: sqlite3.Connection, hash_key: str) -> None:
    """
    把历史失败记录结算为已发布，停止重试。

    用于「记录里已有 typecho_cid」的场景：文章其实已经在站上，只是旧代码在
    更新环节失败留下了 status='failed'。不再更新历史文章之后，这类记录既不会
    被重发（worker 第 6 步后按 typecho_cid 跳过），status 又停在 failed，
    get_retry_due 会每 5 分钟无效回捞一次、永不收敛。

    只改状态字段，不碰 typecho_cid / content_hash 等业务字段。
    """
    now = now_iso()
    conn.execute(
        """
        UPDATE content_posts
        SET status='published', retry_count=0, next_retry_at=NULL,
            error_last=NULL, updated_at=?
        WHERE hash_key=?
        """,
        (now, hash_key),
    )
    conn.commit()


def get_retry_due(
    conn: sqlite3.Connection, now: str, max_retry: int, limit: int = 20
) -> list[dict[str, Any]]:
    """
    返回到期需要重试的记录（status=failed，重试次数未满，到期时间已到）。

    limit 限制单轮批量：队列是单消费者串行的，一次放进太多重试会把新消息
    长时间挡在后面。取最早到期的若干条，剩下的下一轮（5分钟后）继续。
    """
    rows = conn.execute(
        """
        SELECT * FROM content_posts
        WHERE status='failed'
          AND retry_count < ?
          AND next_retry_at <= ?
        ORDER BY next_retry_at ASC
        LIMIT ?
        """,
        (max_retry, now, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def count_retry_pending(conn: sqlite3.Connection, max_retry: int) -> int:
    """待重试记录总数（不含已到期判断）。仅用于日志观测积压是否在收敛。"""
    row = conn.execute(
        "SELECT COUNT(*) FROM content_posts WHERE status='failed' AND retry_count < ?",
        (max_retry,),
    ).fetchone()
    return row[0] or 0


# ── TMDB 缓存 ─────────────────────────────────────────────────────────────────

def get_tmdb_cache(
    conn: sqlite3.Connection, hash_key: str, now: str
) -> dict[str, Any] | None:
    """返回未过期的 TMDB 缓存；过期或不存在返回 None"""
    row = conn.execute(
        "SELECT * FROM tmdb_cache WHERE hash_key=? AND expires_at > ?",
        (hash_key, now),
    ).fetchone()
    return dict(row) if row else None


def save_tmdb_cache(
    conn: sqlite3.Connection,
    hash_key: str,
    query: str,
    media_type: str | None,
    tmdb_id: int | None,
    tmdb_data: dict | None,
    score: int,
    expires_at: str,
) -> None:
    """保存 TMDB 查询结果（包括低分结果，避免重复低分查询）"""
    now = now_iso()
    conn.execute(
        """
        INSERT INTO tmdb_cache
            (hash_key, query, media_type, tmdb_id, tmdb_json, score, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hash_key) DO UPDATE SET
            query      = excluded.query,
            media_type = excluded.media_type,
            tmdb_id    = excluded.tmdb_id,
            tmdb_json  = excluded.tmdb_json,
            score      = excluded.score,
            expires_at = excluded.expires_at,
            updated_at = excluded.updated_at
        """,
        (hash_key, query, media_type, tmdb_id,
         json.dumps(tmdb_data, ensure_ascii=False) if tmdb_data else None,
         score, expires_at, now, now),
    )
    conn.commit()
