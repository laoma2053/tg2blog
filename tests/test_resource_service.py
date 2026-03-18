"""资源服务测试"""
import pytest
from app.services.resource_service import build_resource_candidate, build_summary
from app.schemas.parsed_message import ParsedMessage
from app.schemas.normalized_title import NormalizedTitle


def test_build_resource_candidate():
    """测试构造资源候选对象"""
    parsed = ParsedMessage(
        title_raw="大侦探福尔摩斯",
        description_raw="这是一部精彩的电影",
        tags_raw=["动作", "悬疑"],
        cover_image_url="https://example.com/poster.jpg"
    )

    normalized = NormalizedTitle(
        canonical_title="大侦探福尔摩斯",
        alias_title="Sherlock Holmes",
        year=2009,
        search_keyword="大侦探福尔摩斯"
    )

    candidate = build_resource_candidate(parsed, normalized, "电影")

    assert candidate.canonical_title == "大侦探福尔摩斯"
    assert candidate.year == 2009
    assert candidate.category == "电影"
    assert candidate.description_raw == "这是一部精彩的电影"
    assert "大侦探福尔摩斯" in candidate.summary


def test_build_summary():
    """测试生成摘要"""
    summary = build_summary("流浪地球2")

    assert "流浪地球2" in summary
    assert "zhuiju.us" in summary
