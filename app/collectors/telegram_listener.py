"""Telegram 频道监听器"""
from telethon import TelegramClient, events
from datetime import datetime
from sqlalchemy.orm import Session
from app.schemas.tg_message import TelegramIncomingMessage
from app.services.process_message_service import process_message
from app.db.base import SessionLocal
from app.core.config import settings
from app.core.logger import logger


class TelegramListener:
    """Telegram 频道监听器"""

    def __init__(self):
        self.client = TelegramClient(
            settings.TG_SESSION_NAME,
            settings.TG_API_ID,
            settings.TG_API_HASH
        )
        self.channels = settings.tg_channels_list

    async def start(self):
        """启动监听器"""
        await self.client.start()
        logger.info(f"🚀 Telegram 客户端已启动，监听频道: {self.channels}")

        @self.client.on(events.NewMessage(chats=self.channels))
        async def handler(event):
            await self._handle_message(event)

        await self.client.run_until_disconnected()

    async def _handle_message(self, event):
        """处理新消息"""
        try:
            # 提取消息信息
            channel_id = str(event.chat_id)
            message_id = str(event.message.id)
            raw_text = event.message.text or ""
            message_date = event.message.date

            # 提取封面图
            cover_image_url = None
            if event.message.photo:
                photo = await event.message.download_media(bytes)
                # 这里简化处理，实际应上传到图床
                cover_image_url = f"photo_{message_id}"

            logger.info(f"📨 收到新消息: channel={channel_id}, msg={message_id}")

            # 构造统一消息对象
            incoming_msg = TelegramIncomingMessage(
                channel_id=channel_id,
                channel_name=event.chat.title if hasattr(event.chat, 'title') else None,
                message_id=message_id,
                message_date=message_date,
                raw_text=raw_text,
                cover_image_url=cover_image_url,
                raw_json=event.message.to_dict()
            )

            # 处理消息
            db: Session = SessionLocal()
            try:
                result = process_message(db, incoming_msg)
                logger.info(f"✔️ 消息处理完成: status={result.status}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"❌ 处理消息异常: {str(e)}", exc_info=True)
