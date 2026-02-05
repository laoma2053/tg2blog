import hashlib
import html
import urllib.parse
from typing import Optional

from .parser import ParsedItem


def make_title(item: ParsedItem) -> str:
    # SEO-friendly but not too long
    base = f"《{item.name}》"
    year = f"{item.year}" if item.year else ""
    qual = "4K"
    ep = f" 更新至{item.episode_raw}" if item.episode_raw else ""
    return f"{base} {year} {qual}{ep} 网盘资源".strip()


def make_slug(item: ParsedItem) -> str:
    # simple slug: name-year-4k (keep ascii-safe with URL quoting if non-ascii)
    # WP will sanitize; this is just a suggestion.
    parts = [item.name, str(item.year or ""), "4k"]
    raw = "-".join([p for p in parts if p])
    # keep it short-ish
    return urllib.parse.quote(raw.lower().replace(" ", "-"), safe="-")


def make_zhuiju_search_url(zhuiju_base: str, keyword: str) -> str:
    q = urllib.parse.quote(keyword)
    return (
        f"{zhuiju_base}/s/{q}"
        f"?utm_source=blog&utm_medium=seo&utm_campaign=tg_auto"
    )


def render_html(item: ParsedItem, zhuiju_base: str) -> str:
    title = html.escape(make_title(item))
    zurl = html.escape(make_zhuiju_search_url(zhuiju_base, item.name))

    tags_html = ""
    if item.tags:
        tags_html = "<p><strong>标签：</strong>" + " ".join(
            html.escape(t) for t in item.tags
        ) + "</p>"

    info_lines = []
    info_lines.append(f"<li><strong>片名：</strong>{html.escape(item.name)}</li>")
    if item.year:
        info_lines.append(f"<li><strong>年份：</strong>{item.year}</li>")
    if item.episode_raw:
        info_lines.append(f"<li><strong>更新状态：</strong>{html.escape(item.episode_raw)}</li>")
    if item.size_per_ep:
        info_lines.append(f"<li><strong>体积：</strong>{html.escape(item.size_per_ep)}</li>")
    if item.extra_quality:
        info_lines.append(f"<li><strong>版本说明：</strong>{html.escape(item.extra_quality)}</li>")

    summary_html = ""
    if item.summary:
        # preserve line breaks
        safe = html.escape(item.summary).replace("\n", "<br/>")
        summary_html = f"<p>{safe}</p>"
    else:
        summary_html = "<p>暂无简介（以频道原始信息为准）。</p>"

    html_content = f"""
<h1>{title}</h1>

<h2>资源概览</h2>
<ul>
  {''.join(info_lines)}
</ul>
{tags_html}

<h2>剧情简介</h2>
{summary_html}

<h2>获取方式</h2>
<p>由于资源链接存在时效性，请通过站内获取页获取最新可用版本：</p>
<p><a href="{zurl}" rel="nofollow">👉 点击前往 zhuiju.us 获取《{html.escape(item.name)}》资源</a></p>

<hr/>
<p><em>说明：影片制作信息以官方发布为准；本文仅整理频道发布的版本信息与更新状态。</em></p>
""".strip()

    return html_content


def content_hash(title: str, content: str) -> str:
    h = hashlib.sha1()
    h.update(title.encode("utf-8"))
    h.update(b"\n")
    h.update(content.encode("utf-8"))
    return h.hexdigest()