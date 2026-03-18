"""分类判定器"""
import re
from app.core.constants import (
    CATEGORY_MOVIE, CATEGORY_TV, CATEGORY_ANIME,
    CATEGORY_VARIETY, CATEGORY_SOFTWARE, CATEGORY_COURSE, CATEGORY_OTHER
)


def detect_category(
    title_raw: str | None,
    description_raw: str | None,
    tags_raw: list[str] | None
) -> str:
    """
    根据标题、描述、标签判断资源分类

    Args:
        title_raw: 原始标题
        description_raw: 原始描述
        tags_raw: 原始标签列表

    Returns:
        str: 资源分类
    """
    tags = tags_raw or []
    title = title_raw or ""
    description = description_raw or ""

    # 电影标签
    movie_tags = {"动作", "悬疑", "犯罪", "爱情", "科幻", "喜剧", "恐怖", "惊悚"}
    if any(tag in movie_tags for tag in tags):
        return CATEGORY_MOVIE

    # 剧集特征
    tv_patterns = [r'全\d+集', r'更新至\d+集', r'第\d+集', r'共\d+集']
    for pattern in tv_patterns:
        if re.search(pattern, title) or re.search(pattern, description):
            return CATEGORY_TV

    # 软件特征
    software_patterns = [r'v\d+\.\d+', r'Win/Mac', r'安装包', r'破解', r'\.exe', r'\.dmg']
    for pattern in software_patterns:
        if re.search(pattern, title, re.I):
            return CATEGORY_SOFTWARE

    # 动漫特征
    if "动漫" in tags or "番剧" in tags:
        return CATEGORY_ANIME

    # 综艺特征
    if "综艺" in tags:
        return CATEGORY_VARIETY

    # 课程特征
    if "课程" in title or "教程" in title:
        return CATEGORY_COURSE

    return CATEGORY_OTHER
