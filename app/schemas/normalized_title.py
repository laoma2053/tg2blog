"""标准化标题 Schema"""
from pydantic import BaseModel


class NormalizedTitle(BaseModel):
    """标题标准化结果"""
    canonical_title: str
    alias_title: str | None = None
    year: int | None = None
    search_keyword: str
