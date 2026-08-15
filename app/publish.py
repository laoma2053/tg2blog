"""
Typecho 发布模块 — 通过 MetaWeblog XMLRPC 接口发布和更新文章。
使用内置 xmlrpc.client，通过 run_in_executor 避免阻塞 asyncio 事件循环。
"""
from __future__ import annotations

import asyncio
import logging
import time
import xmlrpc.client
from datetime import datetime, timezone
from functools import partial, lru_cache
from typing import Any

from .config import Config

logger = logging.getLogger(__name__)

# Typecho XMLRPC 固定 blog ID
_BLOG_ID = "1"

# 单次 XMLRPC 超过此耗时记为慢调用
_SLOW_XMLRPC_SEC = 1.0


class _TimeoutTransport(xmlrpc.client.Transport):
    """给 xmlrpc.client 的 HTTP 连接加 socket 超时（标准库默认无超时）"""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host: Any) -> Any:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class _TimeoutSafeTransport(xmlrpc.client.SafeTransport):
    """_TimeoutTransport 的 HTTPS 版本"""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host: Any) -> Any:
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class _RateLimiter:
    """
    固定间隔限流器，保证两次发布之间至少相隔 60/per_minute 秒。

    catch-up 补偿会一次性放出几百条消息，不限流时会以最快速度连续调用
    newPost —— 每次调用都在 Typecho 内部触发若干次 typecho_contents /
    typecho_metas 全表扫描，这是 MySQL CPU 尖峰的直接来源。
    per_minute <= 0 表示不限流。
    """

    def __init__(self, per_minute: int) -> None:
        self._interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = self._next_at - loop.time()
            if wait > 0:
                logger.debug("🐢 发布限流等待 | %.1fs", wait)
                await asyncio.sleep(wait)
            self._next_at = loop.time() + self._interval


class TypechoClient:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        # 关闭 allow_none 兼容性更好；transport 带超时，避免 Typecho 卡死时
        # worker 协程被永久阻塞、队列无界堆积
        transport = (
            _TimeoutSafeTransport(cfg.typecho_timeout)
            if cfg.typecho_xmlrpc_endpoint.lower().startswith("https://")
            else _TimeoutTransport(cfg.typecho_timeout)
        )
        self._server = xmlrpc.client.ServerProxy(
            cfg.typecho_xmlrpc_endpoint, transport=transport
        )
        self._user = cfg.typecho_user
        self._pwd = cfg.typecho_password
        # 分类缓存：name → id，启动时预加载
        self._category_map: dict[str, str] = {}
        # 发布限流：只作用于 newPost / editPost，不限制启动时的分类加载
        self._limiter = _RateLimiter(cfg.max_posts_per_minute)

    # ── 公共方法 ──────────────────────────────────────────────────────────────

    async def load_categories(self) -> None:
        """预加载分类列表到内存，启动时调用一次"""
        cats = await self._call(
            self._server.metaWeblog.getCategories,
            _BLOG_ID, self._user, self._pwd,
        )
        self._category_map = {c["categoryName"]: c["categoryId"] for c in cats}
        logger.debug("🗂️  已加载分类 | 数量=%d", len(self._category_map))

    async def new_post(
        self,
        title: str,
        content: str,
        slug: str,
        category: str,
        tags: list[str],
        excerpt: str = "",
    ) -> int:
        """
        新建文章，返回 Typecho cid（整数）。
        category 若不在后台分类中，Typecho 会使用默认分类。
        """
        struct = _build_struct(title, content, slug, category, tags, excerpt)
        await self._limiter.acquire()
        cid = await self._call(
            self._server.metaWeblog.newPost,
            _BLOG_ID, self._user, self._pwd, struct, True,
        )
        return int(cid)

    async def edit_post(
        self,
        cid: int,
        title: str,
        content: str,
        slug: str,
        category: str,
        tags: list[str],
        excerpt: str = "",
    ) -> None:
        """更新已有文章"""
        struct = _build_struct(title, content, slug, category, tags, excerpt)
        await self._limiter.acquire()
        await self._call(
            self._server.metaWeblog.editPost,
            str(cid), self._user, self._pwd, struct, True,
        )

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    async def _call(self, func: Any, *args: Any) -> Any:
        """在线程池中执行同步 XMLRPC 调用，避免阻塞事件循环"""
        loop = asyncio.get_event_loop()
        started = time.monotonic()
        try:
            return await loop.run_in_executor(None, partial(func, *args))
        except xmlrpc.client.Fault as e:
            raise PublishError(f"XMLRPC Fault {e.faultCode}: {e.faultString}") from e
        except Exception as e:
            raise PublishError(str(e)) from e
        finally:
            elapsed = time.monotonic() - started
            if elapsed > _SLOW_XMLRPC_SEC:
                logger.warning("[SLOW_XMLRPC] method=%s elapsed=%.0fms",
                               getattr(func, "_Method__name", "?"), elapsed * 1000)


class PublishError(Exception):
    """Typecho 发布相关错误，供 worker 捕获"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _build_struct(
    title: str,
    content: str,
    slug: str,
    category: str,
    tags: list[str],
    excerpt: str = "",
) -> dict:
    """构造 MetaWeblog newPost/editPost 所需的 content struct"""
    return {
        "title": title,
        "description": content,
        "mt_excerpt": excerpt,
        # Typecho 通过 categories 数组接收分类名
        "categories": [category],
        # mt_keywords 为逗号分隔的标签字符串
        "mt_keywords": ",".join(tags),
        # wp_slug 设置自定义 URL 别名
        "wp_slug": slug,
        # 发布时间使用当前 UTC 时间
        "dateCreated": xmlrpc.client.DateTime(
            datetime.now(timezone.utc).strftime("%Y%m%dT%H:%M:%S")
        ),
        "post_status": "publish",
    }
