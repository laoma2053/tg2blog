"""
消息解析模块 — 从 TG 原始文本提取影片结构化信息。
策略：第一层严格正则（匹配主流格式）→ 第二层宽松 fallback（覆盖变体）。
解析不到片名时返回 None，由 worker 降级跳过该消息。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .utils import make_hash_key

# ── 正则常量 ──────────────────────────────────────────────────────────────────

# 开头的 emoji 和前缀词（已更新 / 新增 / 上线 / 发布 等变体）
_PREFIX_RE = re.compile(
    r'^[\s\U00010000-\U0010FFFF☀-➿︀-️]*'  # emoji
    r'(?:已更新|新增|上线|发布|更新|首播|完结|最新)?'
    r'[\s:：]*',
    re.UNICODE,
)

# 年份括号：(2026) / （2026） / [2026] 等
_YEAR_RE = re.compile(r'[（(【\[]\s*(\d{4})\s*[）)】\]]')

# EP 信息变体：EP24 / 更至EP24 / 第24集 / 全24集完结
_EP_RE = re.compile(
    r'(?:更至|更新至|至|共)?'
    r'(?:EP(\d+)|第\s*(\d+)\s*集|全\s*(\d+)\s*集)',
    re.IGNORECASE,
)

# 每集体积：5G/集 / 3.5GB/集 / 5G 一集
_SIZE_RE = re.compile(r'体积\s*[：:]\s*([\d.]+\s*[GgMm][Bb]?(?:[/／]集)?)')

# TG hashtag
_TAG_RE = re.compile(r'#(\S+?)(?=[#\s\n]|$)')

# 简介区块标题
_SUMMARY_HEADER_RE = re.compile(r'(?:内容|剧情|故事)?简介')

# 区块起始标志（遇到则停止收集简介）
_SECTION_START_RE = re.compile(r'^[📝🗂🎬📌✦•★▶️]|^(?:获取|资源|标签|信息|下载)')


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ParsedItem:
    name: str
    year: str
    quality_bucket: str = "4k"     # 本系统固定处理 4K 资源
    extra_quality: str = ""         # "臻彩 MAX+ 60FPS 杜比 FLAC" 等
    episode_raw: str = ""           # 原始 EP 文本，用于渲染
    episode_num: int = 0
    size_per_ep: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    raw_title: str = ""
    hash_key: str = ""
    is_series: bool = False         # 有 EP 信息则视为剧集


# ── 公共入口 ──────────────────────────────────────────────────────────────────

def parse(text: str) -> ParsedItem | None:
    """
    解析 TG 消息，返回 ParsedItem。
    片名无法提取时返回 None（消息将被 worker 跳过）。
    """
    if not text or not text.strip():
        return None

    title_line = _first_line(text)

    name = _extract_name(title_line)
    if not name:
        return None

    year = _extract_year(title_line) or ""
    ep_num, ep_raw = _extract_episode(text)
    extra_quality = _extract_quality(title_line)
    size = _extract_size(text)
    tags = _extract_tags(text)
    summary = _extract_summary(text)

    return ParsedItem(
        name=name,
        year=year,
        extra_quality=extra_quality,
        episode_raw=ep_raw,
        episode_num=ep_num,
        size_per_ep=size,
        tags=tags,
        summary=summary,
        raw_title=title_line,
        hash_key=make_hash_key(name, year),
        is_series=ep_num > 0,
    )


# ── 私有解析函数 ──────────────────────────────────────────────────────────────

def _first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _strip_prefix(line: str) -> str:
    """去掉标题行开头的 emoji 和前缀词"""
    return _PREFIX_RE.sub("", line).strip()


def _extract_name(title_line: str) -> str:
    """
    片名提取：年份括号之前的内容即为片名。
    fallback：去掉所有括号内容和4K质量信息后的剩余文字。
    """
    stripped = _strip_prefix(title_line)

    # 第一层：找年份括号
    m = _YEAR_RE.search(stripped)
    if m:
        name = stripped[: m.start()].strip()
        return re.sub(r'[\s\-_|·]+$', "", name)

    # 第二层 fallback：去掉括号内容和4K之后的内容
    name = re.sub(r'[（(【\[][^）)】\]]*[）)】\]]', "", stripped)
    name = re.split(r'4[Kk]', name)[0].strip()
    name = re.sub(r'\s+', " ", name).strip()
    return name[:30] if name else ""  # 片名超过30字说明解析失败


def _extract_year(title_line: str) -> str:
    m = _YEAR_RE.search(title_line)
    return m.group(1) if m else ""


def _extract_episode(text: str) -> tuple[int, str]:
    """返回 (集数, 原始文本)；无集数返回 (0, '')"""
    for m in _EP_RE.finditer(text):
        num = int(m.group(1) or m.group(2) or m.group(3) or 0)
        if num > 0:
            return num, m.group(0).strip()
    return 0, ""


def _extract_quality(title_line: str) -> str:
    """提取 4K 之后、EP 信息之前的画质描述"""
    m4k = re.search(r'4[Kk]', title_line)
    if not m4k:
        return ""
    rest = title_line[m4k.end():]
    ep_m = _EP_RE.search(rest)
    if ep_m:
        rest = rest[: ep_m.start()]
    quality = re.sub(r'[&＆+]', ' ', rest)
    return re.sub(r'\s+', ' ', quality).strip()[:100]


def _extract_size(text: str) -> str:
    m = _SIZE_RE.search(text)
    return m.group(1).strip() if m else ""


def _extract_tags(text: str) -> list[str]:
    """提取 #标签，去重保序"""
    return list(dict.fromkeys(_TAG_RE.findall(text)))


def _extract_summary(text: str) -> str:
    """提取"内容/剧情简介"区块的正文"""
    lines = text.splitlines()
    in_summary = False
    buf: list[str] = []

    for line in lines:
        s = line.strip()
        if _SUMMARY_HEADER_RE.search(s):
            in_summary = True
            continue
        if in_summary:
            if _SECTION_START_RE.match(s):
                break
            if s:
                buf.append(s)

    return "\n".join(buf).strip()
