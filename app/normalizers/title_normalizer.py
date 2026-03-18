"""标题标准化器"""
import re
from app.schemas.normalized_title import NormalizedTitle
from app.core.constants import NOISE_WORDS


def normalize_title(title_raw: str) -> NormalizedTitle:
    """
    标准化标题，提取中文主标题、英文别名、年份和搜索关键词

    Args:
        title_raw: 原始标题

    Returns:
        NormalizedTitle: 标准化结果
    """
    title = title_raw.strip()

    # 提取年份
    year = None
    year_match = re.search(r'\((19|20)\d{2}\)', title)
    if year_match:
        year = int(re.sub(r'[^\d]', '', year_match.group(0)))
        title = title.replace(year_match.group(0), '').strip()
    else:
        year_match = re.search(r'(19|20)\d{2}', title)
        if year_match:
            year = int(year_match.group(0))
            title = title.replace(year_match.group(0), '').strip()

    # 去除噪声词
    for word in NOISE_WORDS:
        title = re.sub(re.escape(word), '', title, flags=re.IGNORECASE).strip()

    # 清理多余空格
    title = re.sub(r'\s+', ' ', title).strip()

    # 尝试拆分中英文
    chinese_part = None
    english_part = None

    # 匹配中文 + 英文模式
    match = re.match(r'^([\u4e00-\u9fff·《》\-—\s]+)\s+([A-Za-z0-9\s\-:\'\"\.]+)$', title)
    if match:
        chinese_part = match.group(1).strip(" 《》")
        english_part = match.group(2).strip()
    else:
        # 只提取中文部分
        chinese_only = re.findall(r'[\u4e00-\u9fff·]+', title)
        if chinese_only:
            chinese_part = ''.join(chinese_only).strip()

    canonical_title = chinese_part if chinese_part else title.strip(" 《》")
    alias_title = english_part
    search_keyword = canonical_title

    return NormalizedTitle(
        canonical_title=canonical_title,
        alias_title=alias_title,
        year=year,
        search_keyword=search_keyword
    )
