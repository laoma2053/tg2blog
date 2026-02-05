import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ParsedItem:
    name: str
    year: Optional[int]
    episode_num: Optional[int]
    episode_raw: Optional[str]
    quality_bucket: str  # fixed "4k" for now; future: 1080p/bluray/web
    extra_quality: str
    size_per_ep: Optional[str]
    tags: List[str]
    summary: Optional[str]


_RE_TITLE_LINE = re.compile(r"^(?:🎬\s*)?(?:已更新[:：]\s*)?(?P<title>.+)$")
_RE_YEAR = re.compile(r"[（(](?P<year>\d{4})[)）]")
_RE_EP = re.compile(r"\bEP\s*(?P<ep>\d{1,4})\b", re.IGNORECASE)
_RE_SIZE = re.compile(r"体积[:：]\s*(?P<size>.+)$")
_RE_TAGS_LINE = re.compile(r"标签[:：]\s*(?P<tags>.+)$")
_RE_HAS_4K = re.compile(r"\b4K\b", re.IGNORECASE)


def _split_sections(text: str) -> Tuple[str, str]:
    """
    Very light section splitter:
    - title line: first non-empty line
    - body: rest
    """
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return "", ""
    return lines[0], "\n".join(lines[1:])


def _normalize_name(s: str) -> str:
    # remove trailing quality phrases and episode phrases, keep first "name(year)" prefix when possible
    s = s.strip()

    # If it contains year, name is before the year bracket
    m = _RE_YEAR.search(s)
    if m:
        prefix = s[: m.start()].strip()
        # also remove leading "已更新："
        prefix = re.sub(r"^已更新[:：]\s*", "", prefix).strip()
        return prefix

    # fallback: take until first space
    return s.split()[0].strip()


def _extract_extra_quality(title: str, name: str, year: Optional[int]) -> str:
    t = title
    # remove name and year from title to keep the rest
    if name:
        t = t.replace(name, " ").strip()
    if year:
        t = re.sub(rf"[（(]{year}[)）]", " ", t).strip()
    # collapse spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_tg_message(raw_text: str) -> ParsedItem:
    title_line, body = _split_sections(raw_text)

    # title line may start with emoji prefix
    m = _RE_TITLE_LINE.match(title_line)
    title = (m.group("title") if m else title_line).strip()

    year = None
    ym = _RE_YEAR.search(title)
    if ym:
        try:
            year = int(ym.group("year"))
        except Exception:
            year = None

    ep_num = None
    ep_raw = None
    em = _RE_EP.search(title)
    if em:
        ep_raw = f"EP{em.group('ep')}"
        try:
            ep_num = int(em.group("ep"))
        except Exception:
            ep_num = None
    else:
        # sometimes EP is in body
        em2 = _RE_EP.search(body)
        if em2:
            ep_raw = f"EP{em2.group('ep')}"
            try:
                ep_num = int(em2.group("ep"))
            except Exception:
                ep_num = None

    name = _normalize_name(title)

    quality_bucket = "4k" if _RE_HAS_4K.search(title) else "4k"  # you said all are 4k
    extra_quality = _extract_extra_quality(title, name, year)

    size_per_ep = None
    tags: List[str] = []
    summary = None

    # parse body lines
    for ln in body.splitlines():
        ln = ln.strip()
        if not ln:
            continue

        sm = _RE_SIZE.search(ln)
        if sm:
            size_per_ep = sm.group("size").strip()
            continue

        tm = _RE_TAGS_LINE.search(ln)
        if tm:
            raw_tags = tm.group("tags")
            # tags in tg often like "#a #b #c"
            tags = [t.strip() for t in raw_tags.split() if t.strip().startswith("#")]
            continue

        # summary begins after "内容简介"
        if ln.startswith("📝 内容简介") or ln.startswith("内容简介"):
            # capture remaining lines after this marker
            # we'll handle below by scanning whole text
            pass

    # summary block extraction
    if "📝 内容简介" in raw_text:
        after = raw_text.split("📝 内容简介", 1)[1]
        # remove leading markers
        after = re.sub(r"^\s*[\r\n]+", "", after)
        # cut off at next section marker if any
        cut_markers = ["📤", "🗂", "🍟", "📬", "💌", "📮", "📎", "资源链接", "频道：", "群组："]
        end_pos = len(after)
        for mk in cut_markers:
            p = after.find(mk)
            if p != -1:
                end_pos = min(end_pos, p)
        summary = after[:end_pos].strip()
        # cleanup possible leading punctuation
        summary = re.sub(r"^[：:\s]+", "", summary).strip() or None

    return ParsedItem(
        name=name or title,
        year=year,
        episode_num=ep_num,
        episode_raw=ep_raw,
        quality_bucket=quality_bucket,
        extra_quality=extra_quality,
        size_per_ep=size_per_ep,
        tags=tags,
        summary=summary,
    )


def build_hash_key(item: ParsedItem) -> str:
    # normalize for stable hash_key
    name_norm = re.sub(r"\s+", "", item.name).lower()
    year = item.year or 0
    return f"{name_norm}_{year}_{item.quality_bucket}"