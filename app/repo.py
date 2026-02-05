import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PostRecord:
    hash_key: str
    wp_post_id: int
    wp_url: Optional[str]
    last_episode_num: Optional[int]
    last_title: Optional[str]
    last_content_hash: Optional[str]


class Repo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_tg_message(
        self,
        channel_username: str,
        msg_id: int,
        msg_date_iso: Optional[str],
        raw_text: str,
        parsed: dict,
        hash_key: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO tg_messages(channel_username, msg_id, msg_date, raw_text, parsed_json, hash_key, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(channel_username, msg_id)
            DO UPDATE SET
              msg_date=excluded.msg_date,
              raw_text=excluded.raw_text,
              parsed_json=excluded.parsed_json,
              hash_key=excluded.hash_key,
              updated_at=excluded.updated_at
            """,
            (
                channel_username,
                msg_id,
                msg_date_iso,
                raw_text,
                json.dumps(parsed, ensure_ascii=False),
                hash_key,
                _now_iso(),
            ),
        )
        self.conn.commit()

    def get_post_by_hash(self, hash_key: str) -> Optional[PostRecord]:
        row = self.conn.execute(
            "SELECT hash_key, wp_post_id, wp_url, last_episode_num, last_title, last_content_hash "
            "FROM content_posts WHERE hash_key=?",
            (hash_key,),
        ).fetchone()
        if not row:
            return None
        return PostRecord(
            hash_key=row["hash_key"],
            wp_post_id=int(row["wp_post_id"]),
            wp_url=row["wp_url"],
            last_episode_num=row["last_episode_num"],
            last_title=row["last_title"],
            last_content_hash=row["last_content_hash"],
        )

    def insert_post(
        self,
        hash_key: str,
        wp_post_id: int,
        wp_url: Optional[str],
        episode_num: Optional[int],
        title: str,
        content_hash: str,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """
            INSERT INTO content_posts(hash_key, wp_post_id, wp_url, last_episode_num, last_title, last_content_hash, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (hash_key, wp_post_id, wp_url, episode_num, title, content_hash, now, now),
        )
        self.conn.commit()

    def update_post(
        self,
        hash_key: str,
        episode_num: Optional[int],
        title: str,
        content_hash: str,
        wp_url: Optional[str] = None,
        status: str = "published",
        error_last: Optional[str] = None,
    ) -> None:
        now = _now_iso()
        self.conn.execute(
            """
            UPDATE content_posts
            SET last_episode_num=?,
                last_title=?,
                last_content_hash=?,
                wp_url=COALESCE(?, wp_url),
                status=?,
                error_last=?,
                updated_at=?
            WHERE hash_key=?
            """,
            (episode_num, title, content_hash, wp_url, status, error_last, now, hash_key),
        )
        self.conn.commit()