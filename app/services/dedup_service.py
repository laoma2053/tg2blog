"""去重服务"""
import re
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from app.db.models import TgMessage, Resource, ResourceLink
from app.schemas.parsed_message import ParsedMessage
from app.schemas.resource import ShareFingerprint
from app.core.constants import (
    DRIVE_TYPE_ALIPAN, DRIVE_TYPE_QUARK, DRIVE_TYPE_BAIDU,
    DRIVE_TYPE_UC, DRIVE_TYPE_XUNLEI
)


def is_duplicate_message(db: Session, channel_id: str, message_id: str) -> bool:
    """
    判断消息是否重复

    Args:
        db: 数据库会话
        channel_id: 频道 ID
        message_id: 消息 ID

    Returns:
        bool: 是否重复
    """
    exists = db.query(TgMessage).filter(
        TgMessage.channel_id == channel_id,
        TgMessage.message_id == message_id
    ).first()
    return exists is not None


def extract_share_fingerprints(parsed: ParsedMessage) -> list[ShareFingerprint]:
    """
    提取网盘链接指纹

    Args:
        parsed: 解析后的消息

    Returns:
        list[ShareFingerprint]: 链接指纹列表
    """
    fingerprints = []

    url_map = {
        DRIVE_TYPE_ALIPAN: parsed.ali_url,
        DRIVE_TYPE_QUARK: parsed.quark_url,
        DRIVE_TYPE_BAIDU: parsed.baidu_url,
        DRIVE_TYPE_UC: parsed.uc_url,
        DRIVE_TYPE_XUNLEI: parsed.xunlei_url,
    }

    for drive_type, url in url_map.items():
        if not url:
            continue

        share_id = _extract_share_id(drive_type, url)
        if share_id:
            fingerprints.append(ShareFingerprint(
                drive_type=drive_type,
                share_id=share_id,
                original_url=url
            ))

    return fingerprints


def _extract_share_id(drive_type: str, url: str) -> str | None:
    """提取分享 ID"""
    if drive_type == DRIVE_TYPE_ALIPAN:
        match = re.search(r'/s/([A-Za-z0-9]+)', url)
        return match.group(1) if match else None

    if drive_type == DRIVE_TYPE_QUARK:
        match = re.search(r'/s/([A-Za-z0-9]+)', url)
        return match.group(1) if match else None

    if drive_type == DRIVE_TYPE_BAIDU:
        match = re.search(r'/s/1([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None

    if drive_type == DRIVE_TYPE_UC:
        match = re.search(r'/s/([A-Za-z0-9]+)', url)
        return match.group(1) if match else None

    if drive_type == DRIVE_TYPE_XUNLEI:
        parsed_url = urlparse(url)
        return parsed_url.path.strip('/') or None

    return None


def find_resource_by_share_fingerprints(
    db: Session,
    fingerprints: list[ShareFingerprint]
) -> Resource | None:
    """
    根据链接指纹查找资源

    Args:
        db: 数据库会话
        fingerprints: 链接指纹列表

    Returns:
        Resource | None: 找到的资源
    """
    for fp in fingerprints:
        link = db.query(ResourceLink).filter(
            ResourceLink.drive_type == fp.drive_type,
            ResourceLink.share_id == fp.share_id
        ).first()

        if link:
            resource = db.query(Resource).filter(
                Resource.id == link.resource_id
            ).first()
            return resource

    return None


def find_resource_by_resource_key(
    db: Session,
    canonical_title: str,
    year: int | None,
    category: str
) -> Resource | None:
    """
    根据资源键查找资源

    Args:
        db: 数据库会话
        canonical_title: 标准标题
        year: 年份
        category: 分类

    Returns:
        Resource | None: 找到的资源
    """
    return db.query(Resource).filter(
        Resource.canonical_title == canonical_title,
        Resource.year == year,
        Resource.category == category
    ).first()
