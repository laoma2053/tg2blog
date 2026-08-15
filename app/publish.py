"""
Typecho 发布模块 — 通过 MetaWeblog XMLRPC 接口发布和更新文章。
使用内置 xmlrpc.client，通过 run_in_executor 避免阻塞 asyncio 事件循环。
"""
from __future__ import annotations

import asyncio
import logging
import time
import xmlrpc.client
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
        # 发布限流：只作用于 newPost / deletePost，不限制启动时的分类加载
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
        # Typecho 的 XMLRPC 层出错时可能返回 0 / 非数字，直接落库会写出一个
        # 永远更新不到的 cid，这里挡在写库之前。
        try:
            cid = int(cid)
        except (TypeError, ValueError):
            raise PublishError(f"newPost 返回非法 cid: {cid!r}")
        if cid <= 0:
            raise PublishError(f"newPost 返回非法 cid: {cid}")
        return cid

    async def delete_post(self, cid: int) -> None:
        """删除文章。cid 不存在时 Typecho 同样返回 true，可安全重复调用。"""
        await self._limiter.acquire()
        await self._call(
            self._server.blogger.deletePost,
            _BLOG_ID, int(cid), self._user, self._pwd, True,
        )

    async def replace_post(
        self,
        cid: int,
        title: str,
        content: str,
        slug: str,
        category: str,
        tags: list[str],
        excerpt: str = "",
    ) -> int:
        """
        更新已有文章 = 删除旧文章 + 用同一个 slug 新建，返回新的 cid。

        不用 metaWeblog.editPost 是因为 Typecho 1.3.0 的 editPost 实际上不更新：
        它把 cid 塞进 $input 后直接调 PostEdit->writePost()，绕过了 action()
        → prepare()，$this->cid 从未被填上，EditTrait::publish() 里的 have()
        恒为 false，于是走 insert() 新建。wp.editPost / blogger.editPost 也都
        转发到同一条路径，同样无效。已实测：对同一 cid 连发两次 editPost，得到
        两个新 cid。

        删除会释放旧 slug，新建能重新拿到干净的 slug（已实测），因此固定链接不变。
        代价：删除成功但新建失败时文章会短暂消失，靠重试补回；重试超限进 dead
        则需要人工处理，记录仍在 content_posts 里可查。
        """
        await self.delete_post(cid)
        return await self.new_post(title, content, slug, category, tags, excerpt)

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
    """构造 MetaWeblog newPost 所需的 content struct"""
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
        # 不传 dateCreated：Typecho 会把收到的时间戳按服务器本地时区（CST）解释，
        # 传 UTC 字符串会让 created 恒早 8 小时。省略时 Typecho 自己取当前时间。
        "post_status": "publish",
    }
