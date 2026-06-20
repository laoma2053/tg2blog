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
        logger.warning("🖼️  图片下载失败 | error=%s", e)
        # 清理可能产生的空文件
        target.unlink(missing_ok=True)

    return results


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
