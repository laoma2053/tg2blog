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
    # 由 retry_loop 重新入队时置 True。消息本就存在于 tg_messages（重试正是从那里
    # 回捞的），若不豁免消息级去重，重试会在 pipeline 第一步就被跳过，永远发不出去。
    is_retry: bool = False


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


async def periodic_catchup(
    client: Any, queue: asyncio.Queue, conn: Any, cfg: Config
) -> None:
    """
    定期无条件补偿 — 不判断为什么漏，只保证漏掉的消息最终会被捞回。

    reconnect_watcher 只在能观测到"断开→重连"状态翻转时才补偿，至少有两类漏检：
    30 秒轮询间隙内完成的快速重连，以及连接始终正常、但服务端不再推送 update
    （此时 is_connected() 全程为 True，任何基于断线检测的方案都无效）。

    正常情况下 min_id 已是最新，每个频道的 iter_messages 立即返回，开销可忽略；
    重复消息由 pipeline 第一步的消息级去重挡掉，不会重复发文。

    局限：只能补回 msg_id 大于 tg_messages 中已记录最大值的消息。中间的空洞
    （如某条消息解析失败未入库、其后的消息已入库）补不回来。
    """
    interval = cfg.periodic_catchup_minutes
    if interval <= 0:
        logger.info("⏸️  定期补偿已禁用 | PERIODIC_CATCHUP_MINUTES=0")
        return

    logger.info("🕐 定期补偿已启用 | 间隔=%d分钟", interval)
    while True:
        await asyncio.sleep(interval * 60)
        # 整体兜住异常：这个协程一旦死掉就静默失效，而它本身正是为了兜住
        # 静默失效而存在的。catch_up 内部已按频道容错，此处防的是意外异常。
        try:
            logger.debug("🕐 定期补偿开始扫描")
            await catch_up(client, queue, conn, cfg, hours=None)
        except Exception as e:
            logger.warning("⚠️  定期补偿失败（下轮重试）| error=%s", e)


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
