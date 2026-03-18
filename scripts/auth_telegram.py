"""
Telegram 认证脚本
在本地运行此脚本完成首次认证，生成 .session 文件
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from telethon import TelegramClient
from app.core.config import settings


async def main():
    print("🔐 开始 Telegram 认证...")
    print(f"📱 API ID: {settings.TG_API_ID}")
    print(f"📂 Session 文件将保存到: {settings.TG_SESSION_NAME}.session")

    client = TelegramClient(
        settings.TG_SESSION_NAME,
        settings.TG_API_ID,
        settings.TG_API_HASH
    )

    await client.start()

    me = await client.get_me()
    print(f"\n✅ 认证成功！")
    print(f"👤 用户: {me.first_name} (@{me.username})")
    print(f"📞 手机: {me.phone}")

    await client.disconnect()
    print(f"\n✨ Session 文件已生成: {settings.TG_SESSION_NAME}.session")
    print("💡 现在可以运行 Docker 容器了")


if __name__ == "__main__":
    asyncio.run(main())
