"""文章服务"""
import random
from app.schemas.resource import ResourceCandidate
from app.schemas.wordpress import WordPressPostPayload
from app.normalizers.slug_builder import build_slug


def build_post_title(canonical_title: str) -> str:
    """
    生成文章标题

    Args:
        canonical_title: 标准标题

    Returns:
        str: 文章标题
    """
    templates = [
        f"{canonical_title} 网盘资源整理",
        f"{canonical_title} 下载资源合集",
        f"{canonical_title} 高清资源获取方式"
    ]
    return random.choice(templates)


def render_post_content(
    candidate: ResourceCandidate,
    slug: str,
    qq_group_url: str,
    qq_channel_url: str,
    backup_quark_url: str,
    backup_baidu_url: str,
    backup_uc_url: str,
    backup_xunlei_url: str,
    go_path_prefix: str = "/go"
) -> str:
    """
    渲染文章正文

    Args:
        candidate: 资源候选对象
        slug: 文章 slug
        其他参数: 各种链接配置

    Returns:
        str: HTML 正文
    """
    content_parts = []

    # 资源简介
    content_parts.append(f"<h2>资源简介</h2>")
    content_parts.append(f"<p>{candidate.summary}</p>")

    # 剧情简介
    if candidate.description_raw:
        content_parts.append(f"<h2>剧情简介</h2>")
        content_parts.append(f"<p>{candidate.description_raw}</p>")

    # 资源信息
    content_parts.append(f"<h2>资源信息</h2>")
    content_parts.append("<ul>")
    content_parts.append(f"<li>名称：{candidate.canonical_title}</li>")
    if candidate.year:
        content_parts.append(f"<li>年份：{candidate.year}</li>")
    content_parts.append(f"<li>类型：{candidate.category}</li>")
    if candidate.size_text:
        content_parts.append(f"<li>大小：{candidate.size_text}</li>")
    if candidate.tags:
        content_parts.append(f"<li>标签：{', '.join(candidate.tags)}</li>")
    content_parts.append("</ul>")

    # 获取方式
    content_parts.append(f"<h2>获取方式</h2>")
    content_parts.append(f'<p><a href="{go_path_prefix}/{slug}">立即获取《{candidate.canonical_title}》资源</a></p>')

    # 社群入口
    content_parts.append(f"<h3>社群入口</h3>")
    content_parts.append("<ul>")
    content_parts.append(f'<li><a href="{qq_group_url}">加入QQ群获取</a></li>')
    content_parts.append(f'<li><a href="{qq_channel_url}">进入QQ频道获取</a></li>')
    content_parts.append("</ul>")

    # 备用获取入口
    content_parts.append(f"<h3>备用获取入口</h3>")
    content_parts.append("<ul>")
    content_parts.append(f'<li><a href="{backup_quark_url}">夸克网盘备用入口</a></li>')
    content_parts.append(f'<li><a href="{backup_baidu_url}">百度网盘备用入口</a></li>')
    content_parts.append(f'<li><a href="{backup_uc_url}">UC网盘备用入口</a></li>')
    content_parts.append(f'<li><a href="{backup_xunlei_url}">迅雷网盘备用入口</a></li>')
    content_parts.append("</ul>")

    return "\n".join(content_parts)


def build_wordpress_payload(
    candidate: ResourceCandidate,
    slug: str,
    content_html: str
) -> WordPressPostPayload:
    """
    构造 WordPress 发布 payload

    Args:
        candidate: 资源候选对象
        slug: 文章 slug
        content_html: HTML 正文

    Returns:
        WordPressPostPayload: WordPress payload
    """
    title = build_post_title(candidate.canonical_title)

    return WordPressPostPayload(
        title=title,
        slug=slug,
        status="publish",
        excerpt=candidate.summary,
        content=content_html,
        categories=[],
        tags=candidate.tags
    )
