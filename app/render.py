"""
文章渲染模块 — 根据融合后的数据生成 Typecho 文章的标题、slug 和 HTML 正文。
正文结构固定，面向 SEO/GEO：无 JS 依赖，内容全部静态可抓取。
"""
from __future__ import annotations

import html
import json
import random
import re
from dataclasses import dataclass
from urllib.parse import quote

from .merge import MergedItem
from . import yaml_cfg
from .utils import to_slug, now_iso


@dataclass
class RenderedPost:
    title: str
    slug: str
    content: str
    excerpt: str
    tags: list[str]
    category: str


def render(item: MergedItem) -> RenderedPost:
    title    = _make_title(item)
    slug     = to_slug(item.name, item.year)
    category = _auto_category(item)
    tags     = _make_tags(item)
    excerpt  = ""  # 留空，由外部插件生成摘要
    content  = _make_html(item, slug)

    return RenderedPost(
        title=title,
        slug=slug,
        content=content,
        excerpt=excerpt,
        tags=tags,
        category=category,
    )


# ── 标题 ──────────────────────────────────────────────────────────────────────

_NETDISK_SUFFIXES = ["夸克网盘资源", "百度网盘资源", "迅雷网盘资源", "UC网盘资源"]


def _make_title(item: MergedItem) -> str:
    base = re.sub(r'^名称[：:]', '', item.raw_title).strip()
    suffix = random.choice(_NETDISK_SUFFIXES)
    return f"已更新：{base} {suffix}"


# ── 分类 ──────────────────────────────────────────────────────────────────────

def _auto_category(item: MergedItem) -> str:
    # 优先使用 TG 前置类型标签（最可靠）
    if item.type_hint:
        return item.type_hint
    # 标签/标题推断
    combined = " ".join(item.tags) + " " + item.raw_title
    if re.search(r'动漫|动画|国漫', combined):
        return "动漫"
    if re.search(r'综艺|真人秀', combined):
        return "综艺"
    if re.search(r'音乐|WAV|FLAC|专辑|无损', combined, re.IGNORECASE):
        return "音乐"
    if item.is_series or item.media_type == "tv":
        return "剧集"
    if "电影" in combined or item.media_type == "movie":
        return "电影"
    return "综合"


# ── 标签 ──────────────────────────────────────────────────────────────────────

def _make_tags(item: MergedItem) -> list[str]:
    tags = list(item.tags)
    quality = item.quality_bucket.upper()
    if quality and quality not in tags:
        tags.append(quality)
    return tags


# ── HTML 正文 ─────────────────────────────────────────────────────────────────

_CAT_SLUG = {
    "剧集": "TVSeries", "电影": "Movie", "综艺": "zongyi",
    "动漫": "dongman", "音乐": "music", "综合": "yingshi",
}


def _make_json_ld(item: MergedItem, slug: str, site: str) -> str:
    """生成 BlogPosting / BreadcrumbList / TVSeries|Movie / FAQPage 四段 JSON-LD"""
    category = _auto_category(item)
    cat_slug  = _CAT_SLUG.get(category, "yingshi")
    url       = f"{site}/archives/{slug}.html"
    desc      = (item.overview or item.summary or "")[:200]
    quality_label = item.quality_bucket.upper() if item.quality_bucket != "hd" else "HD"

    blog_posting = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": f"《{item.name}》{item.year} {quality_label}",
        "description": desc,
        "image": item.cover_image_url or "",
        "datePublished": item.release_date or item.year or "",
        "dateModified": now_iso()[:10],
        "author":    {"@type": "Organization", "name": "网盘追剧资源库"},
        "publisher": {"@type": "Organization", "name": "网盘追剧资源库"},
    }

    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首页",    "item": site},
            {"@type": "ListItem", "position": 2, "name": category,  "item": f"{site}/category/{cat_slug}/"},
            {"@type": "ListItem", "position": 3, "name": item.name, "item": url},
        ],
    }

    media_type = "TVSeries" if item.media_type == "tv" else "Movie"
    media_schema: dict = {
        "@context": "https://schema.org", "@type": media_type,
        "name": item.name, "description": desc,
        "image": item.cover_image_url or "",
        "genre": item.genres[:3],
        "actor": [{"@type": "Person", "name": n} for n in item.cast[:5]],
    }
    if item.release_date:
        media_schema["datePublished"] = item.release_date
    if item.vote_average and item.vote_count:
        media_schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": round(item.vote_average, 1),
            "ratingCount": item.vote_count,
            "bestRating": 10,
        }
    if item.episode_num:
        media_schema["numberOfEpisodes"] = item.episode_num

    ep_text = item.episode_raw or "暂未收录集数信息"
    version_text = quality_label + (f"，{item.extra_quality}" if item.extra_quality else "")
    faq = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "这是什么画质版本？",
             "acceptedAnswer": {"@type": "Answer",
                "text": f"本文整理的是《{item.name}》{item.year}年的 {version_text} 版本。"}},
            {"@type": "Question", "name": "目前更新到第几集？",
             "acceptedAnswer": {"@type": "Answer", "text": f"当前整理状态为：{ep_text}。"}},
            {"@type": "Question", "name": "为什么建议通过站内入口获取？",
             "acceptedAnswer": {"@type": "Answer",
                "text": "影视资源链接经常会失效或更换，通过站内入口可以获取当前最新可用版本，避免打开失效链接。"}},
            {"@type": "Question", "name": "搜索不到怎么办？",
             "acceptedAnswer": {"@type": "Answer",
                "text": f"可以尝试使用片名简称、原名、主演名或年份重新搜索，例如：{item.name}、{item.year}。"}},
            {"@type": "Question", "name": "链接失效怎么办？",
             "acceptedAnswer": {"@type": "Answer",
                "text": f"如果某个网盘入口失效，建议返回 {site} 站内搜索重新获取，系统会尽量展示最新可用的资源入口。"}},
        ],
    }

    return "\n".join(
        f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>'
        for s in [blog_posting, breadcrumb, media_schema, faq]
    )


def _make_html(item: MergedItem, slug: str) -> str:
    """
    结构：JSON-LD → 封面图 → 影片简介 → 影片信息 → 版本信息 → 影评
    → 资源获取 → 常见问题 → 免责声明 → TMDB attribution
    """
    parts: list[str] = []
    site     = yaml_cfg.site_url()
    site_txt = site.replace("https://", "").replace("http://", "")

    # 0. JSON-LD 结构化数据（放正文末尾，避免主题摘要截取时泄露）

    # 1. 封面图
    if item.cover_image_url:
        alt = html.escape(f"{item.name} {item.year} {item.quality_bucket.upper()}".strip())
        parts.append(
            f'<p><img src="{html.escape(item.cover_image_url)}" '
            f'alt="{alt}" style="max-width:100%;" /></p>'
        )

    # 2. 影片简介（TG 描述优先，TMDB overview 备用）
    intro = item.overview or item.summary
    if intro:
        parts.append(
            f"<h2>影片简介</h2>"
            f"<p>{html.escape(intro)}</p>"
        )

    # 3. 影片信息（来自 TMDB）
    info_rows = [
        ("片名",   item.name),
        ("年份",   item.year),
        ("类型",   "、".join(item.genres) if item.genres else ""),
        ("地区",   "、".join(item.countries) if item.countries else ""),
        ("评分",   f"{item.vote_average:.1f}" if item.vote_average else ""),
        ("主演",   "、".join(item.cast[:5]) if item.cast else ""),
    ]
    info_items = "".join(
        f"<li><strong>{k}：</strong>{html.escape(v)}</li>"
        for k, v in info_rows if v
    )
    if info_items:
        parts.append(f"<h2>影片信息</h2><ul>{info_items}</ul>")

    # 4. 版本信息（来自 TG，原样展示）
    quality_label = item.quality_bucket.upper() if item.quality_bucket != "hd" else "HD"
    version_rows = [
        ("画质",     quality_label),
        ("HDR",      item.hdr_type),
        ("编码",     item.encoding),
        ("字幕",     item.subtitle),
        ("音轨",     item.audio),
        ("更新状态", item.episode_raw),
        ("体积",     item.size_per_ep),
    ]
    version_items = "".join(
        f"<li><strong>{k}：</strong>{html.escape(v)}</li>"
        for k, v in version_rows if v
    )
    if version_items:
        parts.append(f"<h2>版本信息</h2><ul>{version_items}</ul>")

    # 5. 影评（TMDB 用户评价）
    if item.reviews:
        review_html = "".join(
            f"<blockquote><p>{html.escape(r[:300])}</p></blockquote>"
            for r in item.reviews
        )
        parts.append(f"<h2>影迷评价</h2>{review_html}")

    # 6. 资源获取（搜索入口 + 网盘保存，合并为一个区块）
    parts.append(_build_resource_section(item, site, site_txt))

    # 7. 常见问题
    name_e   = html.escape(item.name)
    year_e   = html.escape(item.year)
    quality_label = item.quality_bucket.upper() if item.quality_bucket != "hd" else "HD"
    version_e = html.escape(
        f"{quality_label}" + (f"，{item.extra_quality}" if item.extra_quality else "")
    )
    ep_e = html.escape(item.episode_raw or "暂未收录集数信息")
    cast_hint = "、".join(item.cast[:2]) if item.cast else item.name
    parts.append(
        "<h2>常见问题</h2>"
        f"<p><strong>Q：这是什么画质版本？</strong><br>"
        f"A：本文整理的是《{name_e}》{year_e}年的 {version_e} 版本。"
        f"具体画质、音轨和文件规格以实际网盘页面展示为准。</p>"
        f"<p><strong>Q：目前更新到第几集？</strong><br>"
        f"A：当前整理状态为：{ep_e}。如果资源后续更新，本文会根据频道消息同步调整。</p>"
        "<p><strong>Q：为什么建议通过站内入口获取？</strong><br>"
        "A：影视资源链接经常会失效或更换，通过站内入口可以获取当前最新可用版本，避免打开失效链接。</p>"
        f"<p><strong>Q：搜索不到怎么办？</strong><br>"
        f"A：可以尝试使用片名简称、原名、主演名或年份重新搜索，例如：{name_e}、{year_e}"
        f"{('、' + html.escape(cast_hint)) if cast_hint != item.name else ''}。</p>"
        "<p><strong>Q：链接失效怎么办？</strong><br>"
        f'A：如果某个网盘入口失效，建议返回 <a href="{site}" rel="nofollow" target="_blank">'
        f"{html.escape(site_txt)}</a> 站内搜索重新获取，系统会尽量展示最新可用的资源入口。</p>"
    )

    # 8. 免责声明
    parts.append(
        "<hr><p><em>说明：本站仅做影视信息整理与资源索引展示，不存储任何资源文件。"
        "资源入口来自公开网络信息整理，实际可用性以对应页面显示为准。</em></p>"
    )

    # 9. TMDB attribution
    if item.has_tmdb:
        parts.append("<p><small>影片资料来源：TMDB</small></p>")

    # 10. JSON-LD 结构化数据（放末尾，不影响主题摘要截取）
    parts.append(_make_json_ld(item, slug, site))

    return "\n".join(parts)


def _build_resource_section(item: MergedItem, site: str, site_txt: str) -> str:
    _UTM = "utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"

    # 站内搜索——前缀从 config.yaml site.search_prefix 读取
    prefix = yaml_cfg.search_prefix()
    sep = "&" if "?" in prefix else "?"
    search_url = f"{prefix}{quote(item.name)}{sep}{_UTM}"
    prefix_txt = prefix.replace("https://", "").replace("http://", "")
    search_clean = f"{prefix_txt}{item.name}"

    # 备用搜索——前缀为空时不渲染该行
    alt_label = yaml_cfg.alt_search_label()
    alt_prefix = yaml_cfg.alt_search_prefix()
    alt_section = ""
    if alt_prefix:
        alt_sep = "&" if "?" in alt_prefix else "?"
        alt_url = f"{alt_prefix}{quote(item.name)}{alt_sep}{_UTM}"
        alt_prefix_txt = alt_prefix.replace("https://", "").replace("http://", "")
        alt_clean = f"{alt_prefix_txt}{item.name}"
        alt_section = (
            f'<p><strong>{html.escape(alt_label)}：</strong>'
            f'<a href="{html.escape(alt_url)}" rel="nofollow" target="_blank">{html.escape(alt_clean)}</a></p>'
        )

    netdisk_labels = [
        ("夸克网盘", "quark"),
        ("百度网盘", "baidu"),
        ("迅雷网盘", "thunder"),
        ("UC网盘",   "uc"),
    ]
    netdisk_items = "".join(
        f'<li><strong>{label}：</strong>'
        f'<a href="{html.escape(url)}" rel="nofollow noopener noreferrer" target="_blank">{html.escape(url)}</a></li>'
        for label, key in netdisk_labels
        if (url := yaml_cfg.netdisk_links().get(key, ""))
    )
    fallback = (
        f'<p>如果入口暂时不可用，可以返回 <a href="{site}" rel="nofollow" target="_blank">'
        f"{html.escape(site_txt)}</a> 站内搜索页重新获取。</p>"
    )
    return (
        "<h2>资源获取</h2>"
        "<h3>推荐入口</h3>"
        "<p>如果网盘链接失效或无法打开，建议优先通过站内搜索获取最新可用版本：</p>"
        f'<p><strong>站内搜索：</strong>'
        f'<a href="{search_url}" rel="nofollow" target="_blank">{html.escape(search_clean)}</a></p>'
        + alt_section
        + "<h3>网盘入口</h3>"
        "<p>以下入口根据当前收录结果自动展示，资源有效性以实际打开页面为准：</p>"
        f"<ul>{netdisk_items}</ul>"
        + fallback
    )
