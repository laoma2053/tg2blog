"""TG 固定格式消息解析器"""
import re
from app.schemas.parsed_message import ParsedMessage


def parse_tg_message(raw_text: str, cover_image_url: str | None = None) -> ParsedMessage:
    """
    解析 TG 固定格式消息

    Args:
        raw_text: TG 消息原始文本
        cover_image_url: 海报图片 URL

    Returns:
        ParsedMessage: 解析后的结构化数据
    """
    result = ParsedMessage(cover_image_url=cover_image_url)

    # 解析标题
    title_match = re.search(r'^名称[：:]\s*(.+)$', raw_text, re.MULTILINE)
    if title_match:
        result.title_raw = title_match.group(1).strip()

    # 解析描述块
    desc_match = re.search(
        r'描述[：:]\s*(.*?)(?=\n(?:阿里|夸克|百度|UC|迅雷|📁\s*大小|🏷\s*标签)[：:]|\Z)',
        raw_text,
        re.DOTALL
    )
    if desc_match:
        result.description_raw = desc_match.group(1).strip()

    # 解析网盘链接
    patterns = {
        "ali_url": r'阿里[：:]\s*(https?://[^\s]+)',
        "quark_url": r'夸克[：:]\s*(https?://[^\s]+)',
        "baidu_url": r'百度[：:]\s*(https?://[^\s]+)',
        "uc_url": r'UC[：:]\s*(https?://[^\s]+)',
        "xunlei_url": r'迅雷[：:]\s*(https?://[^\s]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            setattr(result, key, match.group(1).strip())

    # 解析大小
    size_match = re.search(r'大小[：:]\s*([^\n]+)', raw_text)
    if size_match:
        result.size_text = size_match.group(1).strip()

    # 解析标签
    tag_line = re.search(r'标签[：:]\s*([^\n]+)', raw_text)
    if tag_line:
        result.tags_raw = re.findall(r'#([^\s#]+)', tag_line.group(1))

    return result
