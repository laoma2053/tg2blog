"""
文章渲染模块 — 根据融合后的数据生成 Typecho 文章的标题、slug 和 HTML 正文。
正文结构固定，面向 SEO/GEO：无 JS 依赖，内容全部静态可抓取。
"""
from __future__ import annotations

import html
from dataclasses import dataclass

from .config import Config
from .merge import MergedItem
from .utils import to_slug


@dataclass
class RenderedPost:
    title: str
    slug: str
    content: str        # 完整 HTML 正文
    tags: list[str]
    category: str


def render(item: MergedItem, cfg: Config) -> RenderedPost:
    """生成可直接发布到 Typecho 的文章对象"""
    title    = _make_title(item)
    slug     = to_slug(item.name, item.year)
    category = _auto_category(item)
    tags     = _make_tags(item)
    content  = _make_html(item, cfg)

    return RenderedPost(
        title=title,
        slug=slug,
        content=content,
        tags=tags,
        category=category,
    )


# ── 标题 ──────────────────────────────────────────────────────────────────────

def _make_title(item: MergedItem) -> str:
    """格式：《片名》年份 4K 更新至EPxx 网盘资源"""
    ep_part = f" 更新至{item.episode_raw}" if item.episode_raw else ""
    year_part = f" {item.year}" if item.year else ""
    return f"《{item.name}》{year_part} 4K{ep_part} 网盘资源"


# ── 分类 ──────────────────────────────────────────────────────────────────────

def _auto_category(item: MergedItem) -> str:
    """自动分类规则（见 MODULES.md §render.py）"""
    if item.is_series:
        return "剧集更新"
    if "电影" in item.tags or item.media_type == "movie":
        return "电影资源"
    return "影视资源"


# ── 标签 ──────────────────────────────────────────────────────────────────────

def _make_tags(item: MergedItem) -> list[str]:
    """TG 原始标签 + 固定 "4K" 标签"""
    tags = list(item.tags)
    if "4K" not in tags:
        tags.append("4K")
    return tags


# ── HTML 正文 ─────────────────────────────────────────────────────────────────

def _make_html(item: MergedItem, cfg: Config) -> str:
    """
    生成固定结构的 HTML 正文：
    封面图 → 资源摘要 → 影片信息 → 版本信息 → 剧情简介
    → 获取方式 → 资源获取 → 常见问题 → 免责声明 → [TMDB attribution]
    """
    parts: list[str] = []

    # 1. 封面图
    if item.cover_image_url:
        alt = html.escape(f"{item.name} {item.year} 4K {item.episode_raw}".strip())
        parts.append(
            f'<p><img src="{html.escape(item.cover_image_url)}" '
            f'alt="{alt}" style="max-width:100%;" /></p>'
        )

    # 2. 资源摘要
    ep_desc = f"，当前更新至{item.episode_raw}" if item.episode_raw else ""
    quality_desc = f"，版本包含 {item.extra_quality}" if item.extra_quality else ""
    parts.append(
        f"<h2>资源摘要</h2>"
        f"<p>《{html.escape(item.name)}》{html.escape(item.year)}年4K版本"
        f"{html.escape(ep_desc)}{html.escape(quality_desc)}。</p>"
    )

    # 3. 影片信息
    info_rows = [
        ("片名", item.name),
        ("年份", item.year),
        ("类型", "、".join(item.genres) if item.genres else ""),
        ("地区", "、".join(item.countries) if item.countries else ""),
        ("评分", f"{item.vote_average:.1f}" if item.vote_average else ""),
        ("主演", "、".join(item.cast[:5]) if item.cast else ""),
    ]
    info_items = "".join(
        f"<li><strong>{k}：</strong>{html.escape(v)}</li>"
        for k, v in info_rows
        if v
    )
    if info_items:
        parts.append(f"<h2>影片信息</h2><ul>{info_items}</ul>")

    # 4. 版本信息
    version_rows = [
        ("画质", "4K"),
        ("版本说明", item.extra_quality),
        ("更新状态", item.episode_raw),
        ("体积", item.size_per_ep),
    ]
    version_items = "".join(
        f"<li><strong>{k}：</strong>{html.escape(v)}</li>"
        for k, v in version_rows
        if v
    )
    parts.append(f"<h2>版本信息</h2><ul>{version_items}</ul>")

    # 5. 剧情简介
    if item.overview:
        parts.append(
            f"<h2>剧情简介</h2>"
            f"<p>{html.escape(item.overview)}</p>"
        )

    # 6. 获取方式（主站导流）
    search_url = (
        f"{cfg.main_site_url}/s/{html.escape(item.name)}"
        "?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"
    )
    parts.append(
        f"<h2>获取方式</h2>"
        f"<p>资源链接会定期更新，请通过以下入口获取最新可用版本：</p>"
        f'<p><a href="{search_url}" rel="nofollow" target="_blank">'
        f"点击前往 {cfg.main_site_url} 获取资源</a></p>"
    )

    # 7. 资源获取（4个网盘固定入口 + 主站搜索）
    # 网盘链接为全站固定链接，由运营方在 .env 中配置，不随影片变化
    netdisk_links = _build_netdisk(item, cfg)
    parts.append(f"<h2>资源获取</h2>{netdisk_links}")

    # 8. 常见问题
    ep_answer = (
        f"当前更新至{item.episode_raw}，以本文显示为准。"
        if item.episode_raw else "请以本文最新更新状态为准。"
    )
    parts.append(
        "<h2>常见问题</h2>"
        "<p><strong>Q：这是4K版本吗？</strong><br>"
        f"A：根据频道发布信息，本资源为4K版本。{html.escape(item.extra_quality) or ''}</p>"
        "<p><strong>Q：资源更新到第几集？</strong><br>"
        f"A：{html.escape(ep_answer)}</p>"
        "<p><strong>Q：如何下载或获取资源？</strong><br>"
        f"A：点击上方网盘入口，或前往 {html.escape(cfg.main_site_url)} 搜索片名获取。</p>"
        "<p><strong>Q：资源是否免费？</strong><br>"
        "A：网盘资源获取入口由第三方提供，具体以对应平台规则为准。</p>"
        "<p><strong>Q：版权相关说明？</strong><br>"
        "A：本站仅做影视信息整理与资源索引展示，不存储、不传播任何受版权保护的文件。</p>"
    )

    # 9. 免责声明
    parts.append(
        "<hr>"
        "<p><em>声明：本站仅做影视信息整理与索引展示，不存储任何资源文件。"
        f"资源获取入口以 {html.escape(cfg.main_site_url)} 页面为准。</em></p>"
    )

    # 10. TMDB attribution（使用了 TMDB 数据时必须展示）
    if item.has_tmdb:
        parts.append(
            "<p><small>部分影片资料来自 TMDB。"
            "本产品使用 TMDB API，但未经 TMDB 认可或认证。</small></p>"
        )

    return "\n".join(parts)


def _build_netdisk(item: MergedItem, cfg: Config) -> str:
    """构造网盘入口区块（固定链接，全站统一）"""
    search_url = (
        f"{cfg.main_site_url}/s/{html.escape(item.name)}"
        "?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto"
    )
    links: list[str] = []
    # 依次展示4个网盘（链接为空则跳过，确保配置后才渲染）
    netdisks = [
        ("夸克网盘", cfg.netdisk_quark),
        ("百度网盘", cfg.netdisk_baidu),
        ("迅雷网盘", cfg.netdisk_thunder),
        ("UC网盘",   cfg.netdisk_uc),
    ]
    for name, url in netdisks:
        if url:
            links.append(
                f'<li><strong>{name}：</strong>'
                f'<a href="{html.escape(url)}" rel="nofollow" target="_blank">'
                f"点击获取</a></li>"
            )
    links.append(
        f'<li><strong>网盘搜索入口：</strong>'
        f'<a href="{search_url}" rel="nofollow" target="_blank">'
        f"{html.escape(cfg.main_site_url)}</a></li>"
    )
    return f"<ul>{''.join(links)}</ul>"
