"""Slug 生成器测试"""
import pytest
from app.normalizers.slug_builder import build_slug


def test_build_slug_chinese():
    """测试中文标题"""
    slug = build_slug("大侦探福尔摩斯")

    assert slug
    assert slug.islower()
    assert all(c.isalnum() or c == '-' for c in slug)


def test_build_slug_consistency():
    """测试同一输入多次生成一致"""
    slug1 = build_slug("流浪地球2")
    slug2 = build_slug("流浪地球2")

    assert slug1 == slug2


def test_build_slug_with_special_chars():
    """测试标题带特殊字符"""
    slug = build_slug("三体：黑暗森林")

    assert slug
    assert all(c.isalnum() or c == '-' for c in slug)
