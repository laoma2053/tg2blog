import logging
import sys

from .config import Settings
from .db import connect, init_db
from .repo import Repo
from .wp_client import WpClient
from .pipeline import RateLimiter, process_message
from .ingest import run_telethon_listener


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    s = Settings.load()
    setup_logging(s.log_level)
    log = logging.getLogger("main")

    conn = connect(s.db_path)
    init_db(conn)
    repo = Repo(conn)

    wp = WpClient(
        base=s.wp_base,
        user=s.wp_user,
        app_pwd=s.wp_app_pwd,
        verify_tls=s.wp_verify_tls,
        timeout=25,
    )

    limiter = RateLimiter(s.max_posts_per_minute)

    def on_message(channel_username, msg_id, msg_date, raw_text):
        process_message(
            repo=repo,
            wp=wp,
            limiter=limiter,
            channel_username=str(channel_username),
            msg_id=int(msg_id),
            msg_date=msg_date,
            raw_text=str(raw_text),
            zhuiju_base=s.zhuiju_base,
        )

    log.info("Starting tg2blog service. DB=%s WP=%s", s.db_path, s.wp_base)

    # Telethon runs an event loop internally
    import asyncio
    asyncio.run(
        run_telethon_listener(
            api_id=s.tg_api_id,
            api_hash=s.tg_api_hash,
            session_dir=s.tg_session_dir,
            channels=s.tg_channels,
            on_message=on_message,
        )
    )


if __name__ == "__main__":
    main()