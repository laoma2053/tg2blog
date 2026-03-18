"""去重服务测试"""
import pytest
from app.services.dedup_service import extract_share_fingerprints
from app.schemas.parsed_message import ParsedMessage
from app.core.constants import DRIVE_TYPE_ALIPAN, DRIVE_TYPE_QUARK


def test_extract_alipan_fingerprint():
    """测试提取阿里云盘指纹"""
    parsed = ParsedMessage(
        ali_url="https://www.alipan.com/s/LqNeerS6idB"
    )

    fingerprints = extract_share_fingerprints(parsed)

    assert len(fingerprints) == 1
    assert fingerprints[0].drive_type == DRIVE_TYPE_ALIPAN
    assert fingerprints[0].share_id == "LqNeerS6idB"


def test_extract_quark_fingerprint():
    """测试提取夸克网盘指纹"""
    parsed = ParsedMessage(
        quark_url="https://pan.quark.cn/s/5284716ccbec"
    )

    fingerprints = extract_share_fingerprints(parsed)

    assert len(fingerprints) == 1
    assert fingerprints[0].drive_type == DRIVE_TYPE_QUARK
    assert fingerprints[0].share_id == "5284716ccbec"


def test_extract_multiple_fingerprints():
    """测试提取多个链接指纹"""
    parsed = ParsedMessage(
        ali_url="https://www.alipan.com/s/abc123",
        quark_url="https://pan.quark.cn/s/xyz789"
    )

    fingerprints = extract_share_fingerprints(parsed)

    assert len(fingerprints) == 2


def test_extract_no_links():
    """测试无链接时返回空列表"""
    parsed = ParsedMessage()

    fingerprints = extract_share_fingerprints(parsed)

    assert fingerprints == []
