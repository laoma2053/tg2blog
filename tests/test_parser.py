"""TG 消息解析器测试"""
import pytest
from app.parsers.tg_message_parser import parse_tg_message


def test_parse_standard_message():
    """测试标准完整样例"""
    raw_text = """名称：大侦探福尔摩斯 Sherlock Holmes (2009)

描述：大侦探福尔摩斯（小罗伯特·唐尼 Robert Downer Jr. 饰）即使在置人于死地之时也异常的逻辑清晰，然而办案时有条不紊的他在私底下的生活中简直就是个"怪胎"。

阿里：https://www.alipan.com/s/LqNeerS6idB
夸克：https://pan.quark.cn/s/5284716ccbec

📁 大小：NG
🏷 标签：#动作 #悬疑 #犯罪"""

    result = parse_tg_message(raw_text, "https://example.com/poster.jpg")

    assert result.title_raw == "大侦探福尔摩斯 Sherlock Holmes (2009)"
    assert "小罗伯特·唐尼" in result.description_raw
    assert result.ali_url == "https://www.alipan.com/s/LqNeerS6idB"
    assert result.quark_url == "https://pan.quark.cn/s/5284716ccbec"
    assert result.size_text == "NG"
    assert result.tags_raw == ["动作", "悬疑", "犯罪"]
    assert result.cover_image_url == "https://example.com/poster.jpg"


def test_parse_missing_ali():
    """测试只有夸克，没有阿里"""
    raw_text = """名称：流浪地球2

夸克：https://pan.quark.cn/s/abc123"""

    result = parse_tg_message(raw_text)

    assert result.quark_url == "https://pan.quark.cn/s/abc123"
    assert result.ali_url is None


def test_parse_no_tags():
    """测试没有标签"""
    raw_text = """名称：三体

描述：科幻小说改编"""

    result = parse_tg_message(raw_text)

    assert result.tags_raw == []


def test_parse_no_size():
    """测试没有大小"""
    raw_text = """名称：测试资源"""

    result = parse_tg_message(raw_text)

    assert result.size_text is None


def test_parse_description_before_tags():
    """测试描述后直接接标签"""
    raw_text = """名称：测试

描述：这是一段描述文字

🏷 标签：#测试"""

    result = parse_tg_message(raw_text)

    assert result.description_raw == "这是一段描述文字"
    assert "标签" not in result.description_raw
