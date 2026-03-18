"""重试发布 pending 状态的资源到 WordPress"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.db.session import get_db
from app.db.models import Resource, Article
from app.schemas.resource import ResourceCandidate
from app.services.article_service import render_post_content, build_wordpress_payload
from app.services.wordpress_publisher import publish_post
from app.normalizers.slug_builder import build_slug
from app.core.config import settings
from app.core.logger import logger


def retry_pending_resources(limit: int = 10) -> dict:
    """
    重试发布 pending 状态的资源

    Args:
        limit: 每次最多处理的资源数量

    Returns:
        dict: 处理统计结果
    """
    db = next(get_db())

    stats = {
        "total": 0,
        "success": 0,
        "failed": 0
    }

    try:
        # 查询 pending 状态的资源
        stmt = select(Resource).where(Resource.status == 'pending').limit(limit)
        pending_resources = db.execute(stmt).scalars().all()

        stats["total"] = len(pending_resources)
        logger.info(f"📋 找到 {stats['total']} 个待发布资源")

        for resource in pending_resources:
            try:
                logger.info(f"🔄 重试发布资源: id={resource.id}, title={resource.canonical_title}")

                # 构造资源候选对象
                candidate = ResourceCandidate(
                    canonical_title=resource.canonical_title,
                    alias_title=resource.alias_title,
                    year=resource.year,
                    category=resource.category,
                    search_keyword=resource.search_keyword,
                    description_raw=resource.description_raw,
                    summary=resource.summary,
                    cover_image_url=resource.cover_image_url,
                    tags=[]
                )

                # 生成文章内容
                slug = build_slug(resource.canonical_title)
                content_html = render_post_content(
                    candidate=candidate,
                    slug=slug,
                    qq_group_url=settings.QQ_GROUP_URL,
                    qq_channel_url=settings.QQ_CHANNEL_URL,
                    backup_quark_url=settings.BACKUP_QUARK_URL,
                    backup_baidu_url=settings.BACKUP_BAIDU_URL,
                    backup_uc_url=settings.BACKUP_UC_URL,
                    backup_xunlei_url=settings.BACKUP_XUNLEI_URL,
                    go_path_prefix=settings.GO_PATH_PREFIX
                )

                payload = build_wordpress_payload(candidate, slug, content_html)

                # 发布到 WordPress
                wp_result = publish_post(payload)

                # 保存文章记录
                article = Article(
                    resource_id=resource.id,
                    wp_post_id=wp_result["id"],
                    wp_slug=wp_result["slug"],
                    title_published=payload.title,
                    status='published'
                )
                db.add(article)

                # 更新资源状态
                resource.status = 'published'
                db.commit()

                stats["success"] += 1
                logger.info(f"✅ 重试成功: resource_id={resource.id}, wp_post_id={wp_result['id']}")

            except Exception as e:
                db.rollback()
                stats["failed"] += 1
                logger.error(f"❌ 重试失败: resource_id={resource.id}, error={str(e)}")
                continue

        logger.info(f"📊 重试完成: 总数={stats['total']}, 成功={stats['success']}, 失败={stats['failed']}")
        return stats

    finally:
        db.close()


if __name__ == "__main__":
    retry_pending_resources()
