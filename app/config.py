import os
from dataclasses import dataclass
from typing import List


def _must(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _opt(name: str, default: str) -> str:
    return os.getenv(name, default)


def _parse_channels(raw: str) -> List[str]:
    # "@a,@b, @c" -> ["@a","@b","@c"]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    # allow without @
    normalized = []
    for p in parts:
        normalized.append(p if p.startswith("@") else f"@{p}")
    return normalized


@dataclass(frozen=True)
class Settings:
    # Telegram
    tg_api_id: int
    tg_api_hash: str
    tg_channels: List[str]
    tg_session_dir: str

    # WordPress
    wp_base: str
    wp_user: str
    wp_app_pwd: str
    wp_verify_tls: bool

    # Business
    zhuiju_base: str

    # Storage
    db_path: str

    # Runtime
    log_level: str
    max_posts_per_minute: int

    @staticmethod
    def load() -> "Settings":
        tg_api_id = int(_must("TG_API_ID"))
        tg_api_hash = _must("TG_API_HASH")
        tg_channels = _parse_channels(_must("TG_CHANNELS"))
        tg_session_dir = _opt("SESSION_DIR", "/data/session")

        wp_base = _must("WP_BASE").rstrip("/")
        wp_user = _must("WP_USER")
        wp_app_pwd = _must("WP_APP_PWD")
        wp_verify_tls = _opt("WP_VERIFY_TLS", "true").lower() in ("1", "true", "yes")

        zhuiju_base = _must("ZHUIJU_BASE").rstrip("/")
        db_path = _opt("DB_PATH", "/data/db/tg2blog.sqlite")

        log_level = _opt("LOG_LEVEL", "INFO").upper()
        max_posts_per_minute = int(_opt("MAX_POSTS_PER_MINUTE", "20"))

        return Settings(
            tg_api_id=tg_api_id,
            tg_api_hash=tg_api_hash,
            tg_channels=tg_channels,
            tg_session_dir=tg_session_dir,
            wp_base=wp_base,
            wp_user=wp_user,
            wp_app_pwd=wp_app_pwd,
            wp_verify_tls=wp_verify_tls,
            zhuiju_base=zhuiju_base,
            db_path=db_path,
            log_level=log_level,
            max_posts_per_minute=max_posts_per_minute,
        )