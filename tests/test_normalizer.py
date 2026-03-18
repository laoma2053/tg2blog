"""标题标准化器测试"""
import pytest
from app.normalizers.title_normalizer import normalize_title


def test_normalize_chinese_english_with_year():
    """测试中英文混排带年份"""
    result = normalize_title("大侦探福尔摩斯 Sherlock Holmes (2009)")

    assert result.canonical_title == "大侦探福尔摩斯"
    assert result.alias_title == "Sherlock Holmes"
    assert result.year == 2009
    assert result.search_keyword == "大侦探福尔摩斯"


def test_normalize_chinese_only():
    """测试只有中文标题"""
    result = normalize_title("流浪地球2 (2023)")

    assert result.canonical_title == "流浪地球2"
    assert result.alias_title is None
    assert result.year == 2023


def test_normalize_with_noise_words():
    """测试带噪声词"""
    result = normalize_title("流浪地球2 4K 国语中字 夸克网盘")

    assert result.search_keyword == "流浪地球2"
    assert "4K" not in result.canonical_title
    assert "夸克" not in result.canonical_title


def test_normalize_english_only():
    """测试只有英文标题"""
    result = normalize_title("Sherlock Holmes (2009)")

    assert result.canonical_title == "Sherlock Holmes"
    assert result.year == 2009


def test_normalize_with_book_marks():
    """测试带书名号"""
    result = normalize_title("《三体》 (2023)")

    assert result.canonical_title == "三体"
    assert result.year == 2023
