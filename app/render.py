"""
文章渲染模块 — 根据融合后的数据生成 Typecho 文章的标题、slug 和 HTML 正文。
正文结构固定，面向 SEO/GEO：无 JS 依赖，内容全部静态可抓取。
"""
from __future__ import annotations

import html
import random
import re
from dataclasses import dataclass
from urllib.parse import quote

from .merge import MergedItem
from . import yaml_cfg
from .utils import to_slug


@dataclass
class RenderedPost:
    title: str
    slug: str
    content: str
    tags: list[str]
    category: str


def render(item: MergedItem) -> RenderedPost:
    title    = _make_title(item)
    slug     = to_slug(item.name, item.year)
    category = _auto_category(item)
    tags     = _make_tags(item)
    content  = _make_html(item)

    return RenderedPost(
        title=title,
        slug=slug,
        content=content,
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
    if item.is_series:
        return "剧集更新"
    if "电影" in item.tags or item.media_type == "movie":
        return "电影资源"
    return "影视资源"


# ── 标签 ──────────────────────────────────────────────────────────────────────

def _make_tags(item: MergedItem) -> list[str]:
    tags = list(item.tags)
    quality = item.quality_bucket.upper()
    if quality and quality not in tags:
        tags.append(quality)
    return tags


# ── HTML 正文 ─────────────────────────────────────────────────────────────────

def _make_html(item: MergedItem) -> str:
    """
    结构：封面图 → 影片简介 → 影片信息 → 版本信息 → 影评
    → 资源获取 → 常见问题 → 免责声明 → TMDB attribution
    """
    parts: list[str] = []
    site     = yaml_cfg.site_url()
    site_txt = site.replace("https://", "").replace("http://", "")

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
        ("版本说明", item.extra_quality),
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
        parts.append(
            "<p><small>部分影片资料来自 TMDB。"
            "本产品使用 TMDB API，但未经 TMDB 认可或认证。</small></p>"
        )

    return "\n".join(parts)


def _build_resource_section(item: MergedItem, site: str, site_txt: str) -> str:
    search_url = (
        f"{site}/s/{quote(item.name)}"
        "?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"
    )
    netdisk_labels = [
        ("夸克网盘", "quark", "前往夸克网盘获取"),
        ("百度网盘", "baidu", "前往百度网盘获取"),
        ("迅雷网盘", "thunder", "前往迅雷网盘获取"),
        ("UC网盘",   "uc",     "前往UC网盘获取"),
    ]
    netdisk_items = "".join(
        f'<li><strong>{label}：</strong>'
        f'<a href="{html.escape(url)}" rel="nofollow" target="_blank">{btn}</a></li>'
        for label, key, btn in netdisk_labels
        if (url := yaml_cfg.netdisk_links().get(key, ""))
    )
    fallback = (
        f'<p>如果入口暂时不可用，可以返回 <a href="{site}" rel="nofollow" target="_blank">'
        f"{html.escape(site_txt)}</a> 站内搜索页重新获取。</p>"
    )
    kuake_url = f"https://www.kuake.so/search?q={quote(item.name)}&platform=quark&utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"
    return (
        "<h2>资源获取</h2>"
        "<h3>推荐入口</h3>"
        "<p>如果网盘链接失效或无法打开，建议优先通过站内搜索获取最新可用版本：</p>"
        f'<p><strong>站内搜索：</strong>'
        f'<a href="{search_url}" rel="nofollow" target="_blank">'
        f"搜索《{html.escape(item.name)}》</a></p>"
        f'<p><strong>备用（夸克）：</strong>'
        f'<a href="{html.escape(kuake_url)}" rel="nofollow" target="_blank">'
        f"搜索《{html.escape(item.name)}》</a></p>"
        "<h3>网盘入口</h3>"
        "<p>以下入口根据当前收录结果自动展示，资源有效性以实际打开页面为准：</p>"
        f"<ul>{netdisk_items}</ul>"
        + fallback
    )
