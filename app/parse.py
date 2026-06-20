"""
消息解析模块 — 从 TG 原始文本提取影片结构化信息。
消息格式：名称：<标题> / 描述：<简介> / 标签：#xx / 大小：...
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .utils import make_hash_key
from . import yaml_cfg

# ── 类型标签映射（前置标签行 → Typecho 分类名）───────────────────────────────
_TYPE_TAG_MAP: dict[str, str] = {
    "剧集": "剧集", "电视剧": "剧集", "短剧": "剧集",
    "电影": "电影",
    "综艺": "综艺", "真人秀": "综艺",
    "动漫": "动漫", "动画": "动漫", "国漫": "动漫",
    "音乐": "音乐",
}

# ── 正则常量 ──────────────────────────────────────────────────────────────────

# 开头前缀（名称 / emoji / 动作词 / 冒号）
_PREFIX_RE = re.compile(
    r'^[\s\U00010000-\U0010FFFF☀-➿︀-️]*'
    r'(?:名称|已更新|新增|上线|发布|更新|首播|完结|最新)?'
    r'[\s:：]*',
    re.UNICODE,
)

# 年份括号：(2026) / （2026） / [2026]
_YEAR_RE = re.compile(r'[（(【\[]\s*(\d{4})\s*[）)】\]]')

# 画质主档位（作为片名的停止边界）
_QUALITY_STOP_RE = re.compile(
    r'\b(4[Kk]|2160[Pp]|1080[Pp]|720[Pp]|480[Pp]|FLAC|BluRay|BDRip)\b',
    re.IGNORECASE,
)

# EP 信息变体：EP24 / 全24集 / 全集 / 更10集 / 已更X集
_EP_RE = re.compile(
    r'(?:更至|更新至|已更|至|共)?'
    r'(?:EP(\d+)|第\s*(\d+)\s*集|全\s*(\d+)\s*集|更\s*(\d+)\s*集|全集)',
    re.IGNORECASE,
)

# 每集体积
_SIZE_RE = re.compile(r'体积\s*[：:]\s*([\d.]+\s*[GgMm][Bb]?(?:[/／]集)?)')

# TG hashtag
_TAG_RE = re.compile(r'#(\S+?)(?=[#\s\n]|$)')

# 可删除行标志
_DELETE_LINE = "（这一行可以删除）"


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ParsedItem:
    name: str
    year: str
    quality_bucket: str = "hd"       # 4k / 1080p / 720p / hd
    extra_quality: str = ""           # HDR、Dv、FLAC 等附加标记
    episode_raw: str = ""             # 原始集数文本，用于渲染
    episode_num: int = 0
    size_per_ep: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""             # 描述：字段内容
    raw_title: str = ""
    hash_key: str = ""
    is_series: bool = False
    skip_tmdb: bool = False           # 短剧/音乐等跳过 TMDB
    type_hint: str = ""               # 前置类型标签推断的分类（如"剧集"/"电影"）


# ── 公共入口 ──────────────────────────────────────────────────────────────────

def parse(text: str) -> ParsedItem | None:
    """
    解析 TG 消息，返回 ParsedItem。
    片名无法提取时返回 None（消息将被 worker 跳过）。
    """
    if not text or not text.strip():
        return None

    clean = _remove_delete_lines(text)
    type_hint, body = _split_type_hint(clean)
    title_line = _strip_markdown(_first_line(body))

    name = _extract_name(title_line)
    if not name:
        return None

    year = _extract_year(title_line) or ""
    ep_num, ep_raw = _extract_episode(body)
    quality_bucket = _detect_quality_bucket(title_line)
    extra_quality = _extract_extra_quality(title_line)
    size = _extract_size(body)
    tags = _extract_tags(body)          # 用 body，避免类型标签混入文章 tags
    description = _extract_description(body)
    skip = _should_skip_tmdb(title_line, tags)

    return ParsedItem(
        name=name,
        year=year,
        quality_bucket=quality_bucket,
        extra_quality=extra_quality,
        episode_raw=ep_raw,
        episode_num=ep_num,
        size_per_ep=size,
        tags=tags,
        description=description,
        raw_title=title_line,
        hash_key=make_hash_key(name, year),
        is_series=ep_num > 0,
        skip_tmdb=skip,
        type_hint=type_hint,
    )


# ── 私有解析函数 ──────────────────────────────────────────────────────────────

def _split_type_hint(text: str) -> tuple[str, str]:
    """
    跳过消息开头的纯类型标签行（如 "#剧集" / "#电影"），
    返回 (type_hint, 去掉类型标签行后的文本)。
    """
    lines = text.splitlines()
    type_hint = ""
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        tags = _TAG_RE.findall(s)
        # 跳过纯分隔符行（如 "."、"-"、"—" 等）
        if re.fullmatch(r'[.\-_—·\s]+', s):
            continue
        # 该行去除所有 #tag 后无剩余实质内容 → 纯标签行
        remainder = re.sub(r'#\S+', '', s).strip()
        if tags and not remainder and all(t in _TYPE_TAG_MAP for t in tags):
            if not type_hint:
                type_hint = _TYPE_TAG_MAP[tags[0]]
            continue
        # 找到第一个非类型标签行，从此处开始作为内容
        return type_hint, "\n".join(lines[i:])
    # 全部是类型标签行（极端情况），返回去掉类型行后的剩余
    content_lines = [l for l in lines if _TAG_RE.findall(l.strip()) == [] or
                     not all(t in _TYPE_TAG_MAP for t in _TAG_RE.findall(l.strip()))]
    return type_hint, "\n".join(content_lines)


def _remove_delete_lines(text: str) -> str:
    """过滤标注了"（这一行可以删除）"的行"""
    return "\n".join(
        line for line in text.splitlines()
        if _DELETE_LINE not in line
    )


def _strip_markdown(text: str) -> str:
    """去掉 Telegram Markdown 格式符（**粗体** / __斜体__ 等）"""
    return re.sub(r'[*_~]{1,2}', '', text)


def _first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _strip_prefix(line: str) -> str:
    """去掉标题行开头的 emoji、'名称：' 等前缀"""
    return _PREFIX_RE.sub("", line).strip()


def _extract_name(title_line: str) -> str:
    """
    片名提取，停止边界（优先级从高到低）：
    1. 年份括号 (2024) / （2024）
    2. 画质标记 4K / 1080P / FLAC …
    3. 集数标记 全X集 / 更X集
    4. 【 开始的属性块
    """
    stripped = _strip_prefix(title_line)

    # 停止点1：年份括号
    m = _YEAR_RE.search(stripped)
    if m:
        name = stripped[: m.start()]
        return _clean_name_tail(name)

    # 停止点2：画质标记
    mq = _QUALITY_STOP_RE.search(stripped)
    if mq:
        name = stripped[: mq.start()]
        return _clean_name_tail(name)

    # 停止点3：集数标记
    me = re.search(r'[全更]\d+集', stripped)
    if me:
        name = stripped[: me.start()]
        return _clean_name_tail(name)

    # 停止点4：【属性块
    mb = stripped.find("【")
    if mb > 0:
        return _clean_name_tail(stripped[:mb])

    # fallback：去括号内容，截30字
    name = re.sub(r'[（(【\[][^）)】\]]*[）)】\]]', "", stripped)
    return re.sub(r'\s+', " ", name).strip()[:30] or ""


def _clean_name_tail(name: str) -> str:
    """去掉片名尾部的空格、标点、横线等"""
    return re.sub(r'[\s\-_|·：:【（(]+$', "", name).strip()


def _extract_year(title_line: str) -> str:
    m = _YEAR_RE.search(title_line)
    return m.group(1) if m else ""


def _detect_quality_bucket(title_line: str) -> str:
    """返回画质档位：4k / 1080p / 720p / hd"""
    if re.search(r'4[Kk]|2160[Pp]', title_line):
        return "4k"
    if re.search(r'1080[Pp]', title_line):
        return "1080p"
    if re.search(r'720[Pp]', title_line):
        return "720p"
    return "hd"


def _extract_extra_quality(title_line: str) -> str:
    """
    提取画质附加标记（HDR / Dv / 杜比 / FLAC / 内封字幕等）。
    优先从 【】 块中提取；fallback 用裸文本匹配。
    """
    qualifiers: list[str] = []
    for b in re.findall(r'【([^】]*)】', title_line):
        b = b.strip()
        if re.search(
            r'HDR|Dv|杜比|Dolby|SDR|码率|FLAC|内封|内嵌|字幕|IQ\.',
            b, re.IGNORECASE
        ):
            qualifiers.append(b)
    if qualifiers:
        return " ".join(qualifiers)
    # fallback
    m = re.search(r'(HDR\d*(?:\s*[+＋])?\s*(?:&|＆)?\s*(?:Dv)?|杜比视界|Dolby)', title_line)
    return m.group(0).strip() if m else ""


def _extract_episode(text: str) -> tuple[int, str]:
    """返回 (集数, 原始文本)；无集数返回 (0, '')"""
    # 先尝试带数字的
    for m in _EP_RE.finditer(text):
        num_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if num_str:
            num = int(num_str)
            if num > 0:
                return num, m.group(0).strip()
    # "全集"不含数字，视为 series 但集数未知
    if re.search(r'全集', text):
        return 1, "全集"
    return 0, ""


def _extract_size(text: str) -> str:
    m = _SIZE_RE.search(text)
    return m.group(1).strip() if m else ""


def _extract_tags(text: str) -> list[str]:
    """提取 #标签，去重保序"""
    return list(dict.fromkeys(_TAG_RE.findall(text)))


def _extract_description(text: str) -> str:
    """
    提取 '描述：' 行及其后续段落内容（至空行/结构行为止）。
    """
    lines = text.splitlines()
    in_desc = False
    buf: list[str] = []

    for line in lines:
        s = line.strip()
        if s.startswith("描述：") or s.startswith("描述:"):
            in_desc = True
            content = re.sub(r'^描述[：:]', "", s).strip()
            if content:
                buf.append(content)
            continue
        if in_desc:
            # 遇到结构行停止
            if s.startswith(("📁", "🏷", "📢", "（", "链接", "阿里", "夸克", "百度", "迅雷")):
                break
            if not s and buf:  # 空行且已有内容，继续收集（允许段落间空行）
                continue
            if s:
                buf.append(s)

    return "\n".join(buf).strip()


def _should_skip_tmdb(title_line: str, tags: list[str]) -> bool:
    """命中 skip_keywords 则跳过 TMDB"""
    keywords = yaml_cfg.tmdb_skip_keywords()
    combined = title_line + " " + " ".join(tags)
    return any(kw in combined for kw in keywords)
