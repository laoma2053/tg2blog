"""资源相关 Schema"""
from pydantic import BaseModel


class ResourceCandidate(BaseModel):
    """资源候选对象"""
    canonical_title: str
    alias_title: str | None = None
    year: int | None = None
    category: str
    search_keyword: str
    description_raw: str | None = None
    summary: str
    cover_image_url: str | None = None
    size_text: str | None = None
    tags: list[str] = []


class ShareFingerprint(BaseModel):
    """网盘链接指纹"""
    drive_type: str
    share_id: str
    original_url: str
