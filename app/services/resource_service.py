"""资源服务"""
from sqlalchemy.orm import Session
from app.db.models import Resource, ResourceLink
from app.schemas.parsed_message import ParsedMessage
from app.schemas.normalized_title import NormalizedTitle
from app.schemas.resource import ResourceCandidate, ShareFingerprint


def build_resource_candidate(
    parsed: ParsedMessage,
    normalized: NormalizedTitle,
    category: str
) -> ResourceCandidate:
    """
    构造资源候选对象

    Args:
        parsed: 解析后的消息
        normalized: 标准化后的标题
        category: 分类

    Returns:
        ResourceCandidate: 资源候选对象
    """
    summary = build_summary(normalized.canonical_title, parsed.description_raw)

    return ResourceCandidate(
        canonical_title=normalized.canonical_title,
        alias_title=normalized.alias_title,
        year=normalized.year,
        category=category,
        search_keyword=normalized.search_keyword,
        description_raw=parsed.description_raw,
        summary=summary,
        cover_image_url=parsed.cover_image_url,
        size_text=parsed.size_text,
        tags=parsed.tags_raw
    )


def build_summary(canonical_title: str, description_raw: str | None = None) -> str:
    """
    生成资源摘要

    Args:
        canonical_title: 标准标题
        description_raw: 原始描述

    Returns:
        str: 摘要文本
    """
    return f'这里整理了《{canonical_title}》的相关资源信息，包括剧情简介、常见网盘来源和获取方式说明。由于资源链接会动态变化，建议前往 zhuiju.us 搜索"{canonical_title}"实时获取最新可用资源。'


def create_resource(db: Session, candidate: ResourceCandidate) -> Resource:
    """
    创建资源记录

    Args:
        db: 数据库会话
        candidate: 资源候选对象

    Returns:
        Resource: 创建的资源
    """
    resource = Resource(
        canonical_title=candidate.canonical_title,
        alias_title=candidate.alias_title,
        year=candidate.year,
        category=candidate.category,
        search_keyword=candidate.search_keyword,
        description_raw=candidate.description_raw,
        summary=candidate.summary,
        cover_image_url=candidate.cover_image_url
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def save_resource_links(
    db: Session,
    resource_id: int,
    fingerprints: list[ShareFingerprint]
) -> None:
    """
    保存资源链接

    Args:
        db: 数据库会话
        resource_id: 资源 ID
        fingerprints: 链接指纹列表
    """
    for fp in fingerprints:
        # 检查是否已存在
        existing = db.query(ResourceLink).filter(
            ResourceLink.drive_type == fp.drive_type,
            ResourceLink.share_id == fp.share_id
        ).first()

        if not existing:
            link = ResourceLink(
                resource_id=resource_id,
                drive_type=fp.drive_type,
                share_id=fp.share_id,
                original_url=fp.original_url
            )
            db.add(link)

    db.commit()
