"""TG 消息相关 Schema"""
from datetime import datetime
from pydantic import BaseModel


class TelegramIncomingMessage(BaseModel):
    """Telegram 监听器接入后的统一输入对象"""
    channel_id: str
    channel_name: str | None = None
    message_id: str
    message_date: datetime | None = None
    raw_text: str
    cover_image_url: str | None = None
    raw_json: dict | None = None
