"""
Typecho 发布模块 — 通过 MetaWeblog XMLRPC 接口发布和更新文章。
使用内置 xmlrpc.client，通过 run_in_executor 避免阻塞 asyncio 事件循环。
"""
from __future__ import annotations

import asyncio
import logging
import xmlrpc.client
from datetime import datetime, timezone
from functools import partial, lru_cache
from typing import Any

from .config import Config

logger = logging.getLogger(__name__)

# Typecho XMLRPC 固定 blog ID
_BLOG_ID = "1"


class TypechoClient:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        # 关闭 allow_none 兼容性更好；transport 不做 SSL 验证（如有需要可扩展）
        self._server = xmlrpc.client.ServerProxy(cfg.typecho_xmlrpc_endpoint)
        self._user = cfg.typecho_user
        self._pwd = cfg.typecho_password
        # 分类缓存：name → id，启动时预加载
        self._category_map: dict[str, str] = {}

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
    ) -> int:
        """
        新建文章，返回 Typecho cid（整数）。
        category 若不在后台分类中，Typecho 会使用默认分类。
        """
        struct = _build_struct(title, content, slug, category, tags)
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
    ) -> None:
        """更新已有文章"""
        struct = _build_struct(title, content, slug, category, tags)
        await self._call(
            self._server.metaWeblog.editPost,
            str(cid), self._user, self._pwd, struct, True,
        )

    # ── 内部工具 ──────────────────────────────────────────────────────────────

    async def _call(self, func: Any, *args: Any) -> Any:
        """在线程池中执行同步 XMLRPC 调用，避免阻塞事件循环"""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, partial(func, *args))
        except xmlrpc.client.Fault as e:
            raise PublishError(f"XMLRPC Fault {e.faultCode}: {e.faultString}") from e
        except Exception as e:
            raise PublishError(str(e)) from e


class PublishError(Exception):
    """Typecho 发布相关错误，供 worker 捕获"""


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _build_struct(
    title: str,
    content: str,
    slug: str,
    category: str,
    tags: list[str],
) -> dict:
    """构造 MetaWeblog newPost/editPost 所需的 content struct"""
    return {
        "title": title,
        "description": content,
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
