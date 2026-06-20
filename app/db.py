"""
数据库模块 — SQLite 连接管理与表结构初始化（幂等）。
WAL 模式允许读写并发，row_factory 让查询结果以字典方式访问。
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .config import Config

logger = logging.getLogger(__name__)


def get_conn(cfg: Config) -> sqlite3.Connection:
    """
    返回一个启用了 WAL 模式的 SQLite 连接。
    check_same_thread=False 允许在 asyncio 协程中使用同一连接。
    """
    db_path = Path(cfg.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row          # 支持 row["field"] 访问
    conn.execute("PRAGMA journal_mode=WAL") # 读写并发，备份安全
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """
    初始化全部表结构，使用 IF NOT EXISTS 保证幂等。
    每次启动都会执行，不会重置已有数据。
    """
    conn.executescript("""
        -- TG 消息记录：消息级去重（channel + msg_id 唯一）
        CREATE TABLE IF NOT EXISTS tg_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel     TEXT    NOT NULL,
            msg_id      INTEGER NOT NULL,
            msg_date    TEXT,
            raw_text    TEXT    NOT NULL,
            parsed_json TEXT,
            hash_key    TEXT,
            is_ad       INTEGER DEFAULT 0,
            updated_at  TEXT    NOT NULL,
            UNIQUE(channel, msg_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tg_hash ON tg_messages(hash_key);

        -- 发布记录：影片级去重（hash_key 唯一），追踪 Typecho 发布状态
        CREATE TABLE IF NOT EXISTS content_posts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            hash_key         TEXT    NOT NULL UNIQUE,
            typecho_cid      INTEGER,
            typecho_url      TEXT,
            last_episode_num INTEGER DEFAULT 0,
            last_title       TEXT,
            content_hash     TEXT,
            cover_image_url  TEXT,
            extra_image_urls TEXT,
            tg_img_hash      TEXT,   -- 上次上传图片的 MD5，相同则跳过重复上传
            tmdb_json        TEXT,
            status           TEXT    NOT NULL DEFAULT 'published',
            retry_count      INTEGER DEFAULT 0,
            next_retry_at    TEXT,   -- ISO8601，NULL 表示无需重试
            error_last       TEXT,
            created_at       TEXT    NOT NULL,
            updated_at       TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_post_status ON content_posts(status, next_retry_at);

        -- TMDB 缓存：避免重复调用 API，缓存有效期见 expires_at
        CREATE TABLE IF NOT EXISTS tmdb_cache (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            hash_key   TEXT    NOT NULL UNIQUE,
            query      TEXT,
            media_type TEXT,
            tmdb_id    INTEGER,
            tmdb_json  TEXT,
            score      INTEGER,
            expires_at TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            updated_at TEXT    NOT NULL
        );
    """)
    conn.commit()
    logger.info("🗄️  数据库初始化完成")
