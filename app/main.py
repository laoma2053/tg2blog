"""
入口模块 — 执行启动序列，启动所有协程，直到服务停止。
启动顺序见 ARCHITECTURE.md §7。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from telethon import TelegramClient

from .config import get_config
from .db import get_conn, init_schema
from . import yaml_cfg
from .listen import catch_up, periodic_catchup, reconnect_watcher, start as listen_start
from .publish import TypechoClient
from .worker import retry_loop, run as worker_run


def _setup_logging(level: str) -> None:
    """简洁日志格式：时间 + 消息（emoji 和中文描述在各模块的 logger 调用中）"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # 抑制 Telethon 和 aiohttp 的 DEBUG 噪音
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


async def main() -> None:
    # 1. 加载并校验配置（缺少必填项时直接退出）
    try:
        cfg = get_config()
    except Exception as e:
        print(f"🔴 启动失败 | 配置错误: {e}", flush=True)
        sys.exit(1)

    _setup_logging(cfg.log_level)

    # 2. 初始化 SQLite
    conn = get_conn(cfg)
    init_schema(conn)

    # 3. 初始化 Typecho 客户端，预加载分类
    publish_client = TypechoClient(cfg)
    try:
        await publish_client.load_categories()
    except Exception as e:
        logger.warning("⚠️  Typecho 分类加载失败（将使用默认分类）| error=%s", e)

    # 4. 创建任务队列（无界，由 asyncio.Queue 默认行为处理背压）
    queue: asyncio.Queue = asyncio.Queue()

    # 5. 初始化 Telethon 客户端
    session_path = str(Path(cfg.session_dir) / "tg2blog")
    tg_client = TelegramClient(session_path, cfg.tg_api_id, cfg.tg_api_hash)

    await tg_client.start()
    logger.info("🔌 Telegram 连接成功")

    # 6. 注册实时监听事件
    listen_start(tg_client, queue, cfg)

    # 7-8. 启动后台协程（保存引用，防止被GC回收导致Task被销毁）
    _tasks = [
        asyncio.ensure_future(retry_loop(queue, conn, cfg)),
        asyncio.ensure_future(worker_run(queue, publish_client, tg_client, conn, cfg)),
    ]

    # 9. catch-up：补偿最近 catchup_hours 内未处理的历史消息（有时间截止）
    await catch_up(tg_client, queue, conn, cfg, hours=cfg.catchup_hours)

    # 10. 重连侦测（检测到断线时快速补偿）+ 定期补偿（兜住检测不到的漏消息场景）
    _tasks.append(asyncio.ensure_future(reconnect_watcher(tg_client, queue, conn, cfg)))
    _tasks.append(asyncio.ensure_future(periodic_catchup(tg_client, queue, conn, cfg)))

    logger.info("🚀 服务启动完成 | 监听频道=%s", ", ".join(yaml_cfg.channels()))

    # 11. 保持运行直到断开
    await tg_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
