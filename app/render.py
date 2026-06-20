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
    ep_answer = (
        f"当前更新至{item.episode_raw}，以本文显示为准。"
        if item.episode_raw else "请以本文最新更新状态为准。"
    )
    parts.append(
        "<h2>常见问题</h2>"
        f"<p><strong>Q：画质和版本如何？</strong><br>"
        f"A：{html.escape(quality_label)}版本。"
        f"{html.escape(item.extra_quality) if item.extra_quality else ''}</p>"
        "<p><strong>Q：资源更新到第几集？</strong><br>"
        f"A：{html.escape(ep_answer)}</p>"
        "<p><strong>Q：如何下载或获取资源？</strong><br>"
        f'A：点击上方网盘入口，或前往 <a href="{site}" rel="nofollow" target="_blank">'
        f"{html.escape(site_txt)}</a> 搜索片名获取。</p>"
        "<p><strong>Q：资源是否免费？</strong><br>"
        "A：网盘资源获取入口由第三方提供，具体以对应平台规则为准。</p>"
        "<p><strong>Q：版权相关说明？</strong><br>"
        "A：本站仅做影视信息整理与资源索引展示，不存储、不传播任何受版权保护的文件。</p>"
    )

    # 8. 免责声明
    parts.append(
        "<hr>"
        "<p><em>声明：本站仅做影视信息整理与索引展示，不存储任何资源文件。"
        f'资源获取入口以 <a href="{site}" rel="nofollow" target="_blank">'
        f"{html.escape(site_txt)}</a> 页面为准。</em></p>"
    )

    # 9. TMDB attribution
    if item.has_tmdb:
        parts.append(
            "<p><small>部分影片资料来自 TMDB。"
            "本产品使用 TMDB API，但未经 TMDB 认可或认证。</small></p>"
        )

    return "\n".join(parts)


def _build_resource_section(item: MergedItem, site: str, site_txt: str) -> str:
    """
    资源获取区块：
    - 方式一：主站搜索
    - 方式二：网盘直接保存（夸克 / 百度 / 迅雷 / UC）
    """
    search_url = (
        f"{site}/s/{quote(item.name)}"
        "?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"
    )

    links: list[str] = [
        f'<li><strong>网站搜索：</strong>'
        f'<a href="{search_url}" rel="nofollow" target="_blank">'
        f"前往 {html.escape(site_txt)} 搜索《{html.escape(item.name)}》</a></li>"
    ]

    netdisks = [
        ("夸克网盘", yaml_cfg.netdisk_links().get("quark", "")),
        ("百度网盘", yaml_cfg.netdisk_links().get("baidu", "")),
        ("迅雷网盘", yaml_cfg.netdisk_links().get("thunder", "")),
        ("UC网盘",   yaml_cfg.netdisk_links().get("uc", "")),
    ]
    for name, url in netdisks:
        if url:
            links.append(
                f'<li><strong>{name}：</strong>'
                f'<a href="{html.escape(url)}" rel="nofollow" target="_blank">'
                f"点击保存</a></li>"
            )

    return f"<h2>资源获取</h2><ul>{''.join(links)}</ul>"
