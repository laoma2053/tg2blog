"""WordPress 相关 Schema"""
from pydantic import BaseModel


class WordPressPostPayload(BaseModel):
    """WordPress 发布 payload"""
    title: str
    slug: str
    status: str = "publish"
    excerpt: str
    content: str
    categories: list[int] | list[str] = []
    tags: list[int] | list[str] = []
    featured_media: int | None = None


class ProcessResult(BaseModel):
    """消息处理结果"""
    status: str  # skip, merged, published, error
    reason: str | None = None
    resource_id: int | None = None
    article_id: int | None = None
    wp_post_id: int | None = None
