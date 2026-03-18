"""解析后的消息 Schema"""
from pydantic import BaseModel


class ParsedMessage(BaseModel):
    """TG 消息解析结果"""
    title_raw: str | None = None
    description_raw: str | None = None
    ali_url: str | None = None
    quark_url: str | None = None
    baidu_url: str | None = None
    uc_url: str | None = None
    xunlei_url: str | None = None
    size_text: str | None = None
    tags_raw: list[str] = []
    cover_image_url: str | None = None
