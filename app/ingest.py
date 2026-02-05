import asyncio
import logging
import os
from typing import Callable, List, Optional

from telethon import TelegramClient, events

log = logging.getLogger("ingest")


def _session_path(session_dir: str) -> str:
    os.makedirs(session_dir, exist_ok=True)
    return os.path.join(session_dir, "telethon.session")


async def run_telethon_listener(
    api_id: int,
    api_hash: str,
    session_dir: str,
    channels: List[str],
    on_message: Callable[[str, int, Optional[object], str], None],
) -> None:
    """
    on_message(channel_username, msg_id, msg_date, raw_text)
    """
    session = _session_path(session_dir)
    client = TelegramClient(session, api_id, api_hash)

    await client.start()  # first run will require interactive login (sms/2fa)
    log.info("Telethon started. Listening channels: %s", ", ".join(channels))

    @client.on(events.NewMessage(chats=channels))
    async def handler_new(event):
        try:
            chat = await event.get_chat()
            username = getattr(chat, "username", None) or str(event.chat_id)
            text = event.raw_text or ""
            on_message(username, event.message.id, event.message.date, text)
        except Exception as e:
            log.exception("NewMessage handler error: %s", e)

    @client.on(events.MessageEdited(chats=channels))
    async def handler_edit(event):
        try:
            chat = await event.get_chat()
            username = getattr(chat, "username", None) or str(event.chat_id)
            text = event.raw_text or ""
            on_message(username, event.message.id, event.message.date, text)
        except Exception as e:
            log.exception("MessageEdited handler error: %s", e)

    await client.run_until_disconnected()