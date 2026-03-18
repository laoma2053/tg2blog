"""WordPress 发布器"""
import httpx
from app.schemas.wordpress import WordPressPostPayload
from app.core.config import settings
from app.core.logger import logger


class WordPressPublishError(Exception):
    """WordPress 发布异常"""
    pass


def publish_post(payload: WordPressPostPayload) -> dict:
    """
    发布文章到 WordPress

    Args:
        payload: WordPress 发布 payload

    Returns:
        dict: WordPress 返回结果，包含 id, slug, link

    Raises:
        WordPressPublishError: 发布失败时抛出
    """
    url = f"{settings.WP_BASE_URL}/wp-json/wp/v2/posts"

    auth = (settings.WP_USERNAME, settings.WP_APP_PASSWORD)

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json=payload.model_dump(),
                auth=auth
            )

            if response.status_code == 201:
                result = response.json()
                logger.info(f"📤 WordPress 发布成功: post_id={result.get('id')}, slug={result.get('slug')}")
                return {
                    "id": result.get("id"),
                    "slug": result.get("slug"),
                    "link": result.get("link")
                }
            else:
                error_msg = f"❌ WordPress 发布失败: status={response.status_code}, body={response.text}"
                logger.error(error_msg)
                raise WordPressPublishError(error_msg)

    except httpx.TimeoutException as e:
        error_msg = f"⏱️ WordPress 发布超时: {str(e)}"
        logger.error(error_msg)
        raise WordPressPublishError(error_msg)
    except httpx.HTTPError as e:
        error_msg = f"🌐 WordPress HTTP 错误: {str(e)}"
        logger.error(error_msg)
        raise WordPressPublishError(error_msg)
