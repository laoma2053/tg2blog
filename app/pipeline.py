import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from .parser import parse_tg_message, build_hash_key
from .renderer import make_title, make_slug, render_html, content_hash
from .repo import Repo
from .wp_client import WpClient


log = logging.getLogger("pipeline")


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class RateLimiter:
    """
    Simple token bucket: max N operations per minute.
    """
    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self.window_start = time.time()
        self.count = 0

    def acquire(self) -> None:
        now = time.time()
        if now - self.window_start >= 60:
            self.window_start = now
            self.count = 0
        if self.count >= self.max_per_minute:
            sleep_s = max(0.0, 60 - (now - self.window_start))
            log.warning("Rate limit reached, sleeping %.1fs", sleep_s)
            time.sleep(sleep_s)
            self.window_start = time.time()
            self.count = 0
        self.count += 1


def process_message(
    repo: Repo,
    wp: WpClient,
    limiter: RateLimiter,
    channel_username: str,
    msg_id: int,
    msg_date: Optional[datetime],
    raw_text: str,
    zhuiju_base: str,
) -> None:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return

    item = parse_tg_message(raw_text)
    hash_key = build_hash_key(item)

    title = make_title(item)
    slug = make_slug(item)
    html = render_html(item, zhuiju_base)
    chash = content_hash(title, html)

    # persist tg message archive (idempotent)
    repo.upsert_tg_message(
        channel_username=channel_username,
        msg_id=msg_id,
        msg_date_iso=_to_iso(msg_date),
        raw_text=raw_text,
        parsed=asdict(item),
        hash_key=hash_key,
    )

    existing = repo.get_post_by_hash(hash_key)
    if not existing:
        limiter.acquire()
        try:
            created = wp.create_post(title=title, content=html, slug=slug, status="publish")
            repo.insert_post(
                hash_key=hash_key,
                wp_post_id=created.post_id,
                wp_url=created.link,
                episode_num=item.episode_num,
                title=title,
                content_hash=chash,
            )
            log.info("CREATED post hash=%s wp_post_id=%s title=%s", hash_key, created.post_id, title)
        except Exception as e:
            repo.update_post(hash_key=hash_key, episode_num=item.episode_num, title=title, content_hash=chash,
                             status="failed", error_last=str(e))
            log.exception("CREATE failed hash=%s err=%s", hash_key, e)
        return

    # decide whether to update
    should_update = False

    # 1) content changed
    if existing.last_content_hash != chash:
        should_update = True

    # 2) episode increased (strong signal)
    if item.episode_num is not None:
        old_ep = existing.last_episode_num
        if old_ep is None or item.episode_num > old_ep:
            should_update = True

    if not should_update:
        log.info("SKIP no change hash=%s wp_post_id=%s", hash_key, existing.wp_post_id)
        return

    limiter.acquire()
    try:
        updated = wp.update_post(post_id=existing.wp_post_id, title=title, content=html, slug=slug)
        repo.update_post(
            hash_key=hash_key,
            episode_num=item.episode_num,
            title=title,
            content_hash=chash,
            wp_url=updated.link,
            status="published",
            error_last=None,
        )
        log.info("UPDATED post hash=%s wp_post_id=%s title=%s", hash_key, updated.post_id, title)
    except Exception as e:
        repo.update_post(hash_key=hash_key, episode_num=item.episode_num, title=title, content_hash=chash,
                         status="failed", error_last=str(e))
        log.exception("UPDATE failed hash=%s wp_post_id=%s err=%s", hash_key, existing.wp_post_id, e)