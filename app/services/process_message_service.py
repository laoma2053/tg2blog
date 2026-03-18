"""消息处理主流程"""
from sqlalchemy.orm import Session
from app.schemas.tg_message import TelegramIncomingMessage
from app.schemas.wordpress import ProcessResult
from app.db.models import TgMessage, Article
from app.parsers.tg_message_parser import parse_tg_message
from app.normalizers.title_normalizer import normalize_title
from app.normalizers.slug_builder import build_slug
from app.services.category_detector import detect_category
from app.services.dedup_service import (
    is_duplicate_message, extract_share_fingerprints,
    find_resource_by_share_fingerprints, find_resource_by_resource_key
)
from app.services.resource_service import (
    build_resource_candidate, create_resource, save_resource_links
)
from app.services.article_service import render_post_content, build_wordpress_payload
from app.services.wordpress_publisher import publish_post
from app.core.config import settings
from app.core.logger import logger
from app.core.constants import STATUS_SKIP, STATUS_MERGED, STATUS_PUBLISHED, STATUS_ERROR


def process_message(db: Session, message: TelegramIncomingMessage) -> ProcessResult:
    """
    处理 TG 消息主流程

    Args:
        db: 数据库会话
        message: TG 消息

    Returns:
        ProcessResult: 处理结果
    """
    try:
        # 1. 判断重复消息
        if is_duplicate_message(db, message.channel_id, message.message_id):
            logger.info(f"⏭️ 跳过重复消息: channel={message.channel_id}, msg={message.message_id}")
            return ProcessResult(status=STATUS_SKIP, reason="duplicate_message")

        # 2. 保存原始消息
        tg_msg = TgMessage(
            channel_id=message.channel_id,
            channel_name=message.channel_name,
            message_id=message.message_id,
            message_date=message.message_date,
            raw_text=message.raw_text,
            raw_image_url=message.cover_image_url,
            raw_json=message.raw_json
        )
        db.add(tg_msg)
        db.commit()

        # 3. 解析消息
        parsed = parse_tg_message(message.raw_text, message.cover_image_url)
        logger.info(f"📝 解析消息成功: {parsed.title_raw}")

        # 4. 标题标准化
        if not parsed.title_raw:
            logger.warning("⚠️ 标题为空，跳过处理")
            return ProcessResult(status=STATUS_SKIP, reason="empty_title")

        normalized = normalize_title(parsed.title_raw)
        logger.info(f"✨ 标题标准化: {normalized.canonical_title}")

        # 5. 分类判定
        category = detect_category(parsed.title_raw, parsed.description_raw, parsed.tags_raw)

        # 6. 构造资源候选对象
        candidate = build_resource_candidate(parsed, normalized, category)

        # 7. 提取链接指纹
        fingerprints = extract_share_fingerprints(parsed)

        # 8. 链接级去重
        existing_resource = find_resource_by_share_fingerprints(db, fingerprints)
        if existing_resource:
            save_resource_links(db, existing_resource.id, fingerprints)
            logger.info(f"🔗 链接去重命中: resource_id={existing_resource.id}")
            return ProcessResult(
                status=STATUS_MERGED,
                reason="duplicate_by_link",
                resource_id=existing_resource.id
            )

        # 9. 资源级去重
        existing_resource = find_resource_by_resource_key(
            db, normalized.canonical_title, normalized.year, category
        )
        if existing_resource:
            save_resource_links(db, existing_resource.id, fingerprints)
            logger.info(f"📦 资源去重命中: resource_id={existing_resource.id}")
            return ProcessResult(
                status=STATUS_MERGED,
                reason="duplicate_by_resource_key",
                resource_id=existing_resource.id
            )

        # 10. 创建资源
        resource = create_resource(db, candidate)
        logger.info(f"✅ 资源创建成功: resource_id={resource.id}")

        # 11. 保存资源链接
        save_resource_links(db, resource.id, fingerprints)

        # 12. 构造文章
        slug = build_slug(normalized.canonical_title)
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

        # 13. 发布 WordPress
        wp_result = publish_post(payload)

        # 14. 保存文章记录
        article = Article(
            resource_id=resource.id,
            wp_post_id=wp_result["id"],
            wp_slug=wp_result["slug"],
            title_published=payload.title
        )
        db.add(article)
        db.commit()

        logger.info(f"🎉 文章发布成功: article_id={article.id}, wp_post_id={wp_result['id']}")

        # 15. 返回结果
        return ProcessResult(
            status=STATUS_PUBLISHED,
            resource_id=resource.id,
            article_id=article.id,
            wp_post_id=wp_result["id"]
        )

    except Exception as e:
        logger.error(f"❌ 处理消息失败: {str(e)}", exc_info=True)
        db.rollback()
        return ProcessResult(status=STATUS_ERROR, reason=str(e))
