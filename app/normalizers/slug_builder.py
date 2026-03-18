"""Slug 生成器"""
from slugify import slugify
from pypinyin import lazy_pinyin


def build_slug(canonical_title: str) -> str:
    """
    生成 URL 安全的 slug

    Args:
        canonical_title: 标准化后的标题

    Returns:
        str: URL 安全的 slug
    """
    # 将中文转换为拼音
    pinyin_parts = lazy_pinyin(canonical_title)
    pinyin_text = '-'.join(pinyin_parts)

    # 使用 slugify 生成最终 slug
    slug = slugify(pinyin_text, lowercase=True)

    # 确保不返回空字符串
    if not slug:
        slug = "resource"

    return slug
