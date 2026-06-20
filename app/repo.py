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
) -> None:
    """新建或更新发布记录（发布成功时调用）"""
    now = now_iso()
    conn.execute(
        """
        INSERT INTO content_posts
            (hash_key, typecho_cid, typecho_url, last_title, last_episode_num,
             content_hash, cover_image_url, extra_image_urls, tg_img_hash,
             tmdb_json, status, retry_count, next_retry_at, error_last, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', 0, NULL, NULL, ?, ?)
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


def get_retry_due(
    conn: sqlite3.Connection, now: str, max_retry: int
) -> list[dict[str, Any]]:
    """返回到期需要重试的记录（status=failed，重试次数未满，到期时间已到）"""
    rows = conn.execute(
        """
        SELECT * FROM content_posts
        WHERE status='failed'
          AND retry_count < ?
          AND next_retry_at <= ?
        """,
        (max_retry, now),
    ).fetchall()
    return [dict(r) for r in rows]


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
