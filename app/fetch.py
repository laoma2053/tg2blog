"""
TG 图片下载模块 — 从 TG 消息下载图片到本地临时目录。
支持 message.photo 和文档类型图片（JPEG/PNG）。
下载失败不抛出异常，返回空列表，由 pipeline 降级处理。
临时文件由调用方（worker）负责清理。
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from .utils import file_md5

logger = logging.getLogger(__name__)

# 临时图片目录，容器启动时已创建
_TMP_DIR = Path("/tmp/tg2blog")

# 允许下载的文档 MIME 类型
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


@dataclass
class FetchedImage:
    local_path: str
    img_hash: str   # MD5，用于判断是否与上次相同（避免重复上传）


async def download(message: object, client: object) -> list[FetchedImage]:
    """
    下载消息中的图片，返回 FetchedImage 列表。
    message 为 Telethon Message 对象；client 为 TelegramClient。
    """
    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    results: list[FetchedImage] = []

    # 判断图片来源：photo 字段 或 document 类型图片
    media = getattr(message, "photo", None) or _get_image_doc(message)
    if not media:
        return results

    target = _TMP_DIR / f"{uuid.uuid4().hex}.jpg"
    try:
        await client.download_media(message, file=str(target))
        if target.exists() and target.stat().st_size > 0:
            results.append(FetchedImage(
                local_path=str(target),
                img_hash=file_md5(str(target)),
            ))
    except Exception as e:
        target.unlink(missing_ok=True)
        err_str = str(e).lower()
        # file_reference 过期：重新从 TG 拉取消息以刷新引用，重试一次
        if "file reference" in err_str and "expired" in err_str:
            logger.debug("🔄 file_reference 已过期，尝试刷新后重试 | msg_id=%s",
                         getattr(message, "id", "?"))
            fetched = await _retry_with_fresh_ref(message, client)
            if fetched:
                results.append(fetched)
            else:
                logger.warning("🖼️  图片下载失败（刷新引用后仍失败） | msg_id=%s",
                               getattr(message, "id", "?"))
        else:
            logger.warning("🖼️  图片下载失败 | error=%s", e)

    return results


async def _retry_with_fresh_ref(message: object, client: object) -> "FetchedImage | None":
    """
    file_reference 过期时，重新向 TG 拉取该消息以获取新的引用，再重试下载一次。
    失败则返回 None，由调用方降级处理。
    """
    try:
        peer = getattr(message, "peer_id", None) or getattr(message, "chat_id", None)
        msg_id = getattr(message, "id", None)
        if peer is None or msg_id is None:
            return None

        fresh = await client.get_messages(peer, ids=msg_id)
        if not fresh:
            return None

        target = _TMP_DIR / f"{uuid.uuid4().hex}.jpg"
        await client.download_media(fresh, file=str(target))
        if target.exists() and target.stat().st_size > 0:
            return FetchedImage(
                local_path=str(target),
                img_hash=file_md5(str(target)),
            )
        target.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("🖼️  图片下载失败（刷新引用后仍失败） | error=%s", e)
    return None


def cleanup(images: list[FetchedImage]) -> None:
    """清理所有临时图片文件，pipeline 发布完成后调用"""
    for img in images:
        try:
            os.unlink(img.local_path)
        except OSError:
            pass


def _get_image_doc(message: object) -> object | None:
    """从 message.document 中识别图片类型附件"""
    doc = getattr(message, "document", None)
    if not doc:
        return None
    mime = getattr(doc, "mime_type", "") or ""
    return doc if mime in _ALLOWED_MIME else None
