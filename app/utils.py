"""
公共工具函数 — 供各模块调用的纯函数，无副作用，无外部依赖。
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from pypinyin import Style, lazy_pinyin


def normalize_name(name: str) -> str:
    """标准化片名，用于生成 hash_key（去空格、转小写）"""
    name = re.sub(r'\s+', '', name)
    return name.lower()


def make_hash_key(name: str, year: str) -> str:
    """生成影片唯一去重键，格式：normalize(name)_year_4k"""
    return f"{normalize_name(name)}_{year}_4k"


def content_hash(episode_num: int, extra_quality: str, size_per_ep: str) -> str:
    """
    基于资源核心字段计算内容指纹。
    只有这三个字段变化才触发 Typecho 文章更新，避免无意义写入。
    """
    raw = f"{episode_num}|{extra_quality}|{size_per_ep}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def file_md5(path: str) -> str:
    """计算文件 MD5，用于图片去重复上传"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def to_slug(name: str, year: str) -> str:
    """
    中文片名转拼音 slug，例：太平年 → tai-ping-nian-2026-4k
    pypinyin 自动处理汉字；英文字符直接保留。
    """
    pinyin_parts = lazy_pinyin(name, style=Style.NORMAL)
    raw = "-".join(pinyin_parts) + f"-{year}-4k"
    # 只保留字母、数字、连字符
    slug = re.sub(r'[^a-z0-9-]', '-', raw.lower())
    return re.sub(r'-{2,}', '-', slug).strip('-')


def now_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串"""
    return datetime.now(timezone.utc).isoformat()


def truncate(text: str, max_len: int = 120) -> str:
    """截断过长文本，用于日志输出"""
    return text[:max_len] + "…" if len(text) > max_len else text
