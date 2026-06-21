"""
TG 监听模块 — 注册实时事件（NewMessage + MessageEdited）并执行 catch-up。
catch-up 在服务启动时运行一次，补偿最近 catchup_hours 小时内未处理的历史消息。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from telethon import events

from . import repo
from . import yaml_cfg
from .config import Config
from .utils import now_iso

logger = logging.getLogger(__name__)


@dataclass
class RawMessage:
    """队列中流转的消息单元"""
    channel: str        # 频道用户名（@xxx），用作数据库键，保持稳定
    msg_id: int
    msg_date: str
    text: str
    is_edit: bool
    message: Any        # Telethon Message 对象，重试模式下为 None（跳过图片下载）
    channel_title: str = ""  # 频道显示名（中文名），仅用于日志/通知


def start(client: Any, queue: asyncio.Queue, cfg: Config) -> None:
    """
    注册 NewMessage 和 MessageEdited 事件处理器。
    监听 cfg.tg_channels 中的所有频道。
    """
    channels = yaml_cfg.channels()

    @client.on(events.NewMessage(chats=channels))
    async def _on_new(event: Any) -> None:
        msg = event.message
        if not msg.text:
            return
        await queue.put(RawMessage(
            channel=_channel_name(event),
            channel_title=getattr(getattr(event, "chat", None), "title", None) or "",
            msg_id=msg.id,
            msg_date=msg.date.isoformat() if msg.date else now_iso(),
            text=msg.text,
            is_edit=False,
            message=msg,
        ))
        logger.debug("📨 收到新消息 | channel=%s msg_id=%d", _channel_name(event), msg.id)

    @client.on(events.MessageEdited(chats=channels))
    async def _on_edit(event: Any) -> None:
        msg = event.message
        if not msg.text:
            return
        await queue.put(RawMessage(
            channel=_channel_name(event),
            channel_title=getattr(getattr(event, "chat", None), "title", None) or "",
            msg_id=msg.id,
            msg_date=msg.date.isoformat() if msg.date else now_iso(),
            text=msg.text,
            is_edit=True,
            message=msg,
        ))
        logger.debug("✏️  收到编辑消息 | channel=%s msg_id=%d", _channel_name(event), msg.id)

    logger.info("👂 开始监听 | 频道=%s", ", ".join(channels))


async def catch_up(
    client: Any, queue: asyncio.Queue, conn: Any, cfg: Config, hours: int | None = None
) -> None:
    """
    补偿历史消息。hours=None 时不设时间截止，仅依赖 min_id 限边界（用于定期补偿）；
    hours 有值时额外加时间截止（用于启动时的初始 catch-up）。
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=hours or cfg.catchup_hours)
        if hours is not None else None
    )

    for channel in yaml_cfg.channels():
        last_id = repo.get_last_msg_id(conn, channel)
        count = 0

        try:
            async for msg in client.iter_messages(channel, min_id=last_id):
                # 有时间截止时，超出窗口则停止（启动模式）
                if cutoff and msg.date and msg.date.replace(tzinfo=timezone.utc) < cutoff:
                    break
                if not msg.text:
                    continue
                await queue.put(RawMessage(
                    channel=channel,
                    channel_title=getattr(getattr(msg, "chat", None), "title", None) or "",
                    msg_id=msg.id,
                    msg_date=msg.date.isoformat() if msg.date else now_iso(),
                    text=msg.text,
                    is_edit=False,
                    message=msg,
                ))
                count += 1
        except Exception as e:
            logger.warning("⚠️  catch-up 失败 | channel=%s error=%s", channel, e)
            continue

        if count:
            logger.info("⏪ 补偿历史消息 | 频道=%s 发现=%d条", channel, count)


async def reconnect_watcher(
    client: Any, queue: asyncio.Queue, conn: Any, cfg: Config
) -> None:
    """
    重连侦测 — 每30秒检查一次连接状态。
    检测到断线→重连时立即触发 catch_up，补偿断线期间的所有遗漏消息。
    """
    was_connected = True
    while True:
        await asyncio.sleep(30)
        is_conn = client.is_connected()
        if not was_connected and is_conn:
            logger.info("🔌 检测到重连，开始补偿断线期间遗漏消息")
            await catch_up(client, queue, conn, cfg, hours=None)
        was_connected = is_conn


def _channel_name(event: Any) -> str:
    """从 event 提取频道用户名或 ID"""
    chat = getattr(event, "chat", None)
    if chat:
        username = getattr(chat, "username", None)
        if username:
            return f"@{username}"
        return str(getattr(chat, "id", "unknown"))
    return "unknown"
