import sqlite3


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tg_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_username TEXT NOT NULL,
  msg_id INTEGER NOT NULL,
  msg_date TEXT,
  raw_text TEXT NOT NULL,
  parsed_json TEXT,
  hash_key TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(channel_username, msg_id)
);

CREATE TABLE IF NOT EXISTS content_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash_key TEXT NOT NULL UNIQUE,
  wp_post_id INTEGER NOT NULL,
  wp_url TEXT,
  last_episode_num INTEGER,
  last_title TEXT,
  last_content_hash TEXT,
  status TEXT NOT NULL DEFAULT 'published',
  error_last TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tg_messages_hash_key ON tg_messages(hash_key);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()