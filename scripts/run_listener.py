"""运行 Telegram 监听器"""
import asyncio
from app.collectors.telegram_listener import TelegramListener
from app.core.logger import logger


async def main():
    """主函数"""
    logger.info("🚀 启动 tg2blog 监听器...")
    listener = TelegramListener()
    await listener.start()


if __name__ == "__main__":
    asyncio.run(main())
