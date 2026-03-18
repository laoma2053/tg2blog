"""文章服务测试"""
import pytest
from app.services.article_service import build_post_title, render_post_content, build_wordpress_payload
from app.schemas.resource import ResourceCandidate


def test_build_post_title():
    """测试生成文章标题"""
    title = build_post_title("大侦探福尔摩斯")

    assert "大侦探福尔摩斯" in title
    assert title  # 非空


def test_render_post_content():
    """测试渲染文章正文"""
    candidate = ResourceCandidate(
        canonical_title="大侦探福尔摩斯",
        alias_title="Sherlock Holmes",
        year=2009,
        category="电影",
        search_keyword="大侦探福尔摩斯",
        description_raw="精彩的侦探电影",
        summary="这是摘要",
        tags=["动作", "悬疑"]
    )

    content = render_post_content(
        candidate=candidate,
        slug="da-zhen-tan-fu-er-mo-si",
        qq_group_url="https://qm.qq.com/test",
        qq_channel_url="https://pd.qq.com/test",
        backup_quark_url="https://quark.test",
        backup_baidu_url="https://baidu.test",
        backup_uc_url="https://uc.test",
        backup_xunlei_url="https://xunlei.test"
    )

    # 检查必须包含的区块
    assert "资源简介" in content
    assert "剧情简介" in content
    assert "资源信息" in content
    assert "获取方式" in content
    assert "社群入口" in content
    assert "备用获取入口" in content

    # 检查主入口链接
    assert "/go/da-zhen-tan-fu-er-mo-si" in content

    # 检查社群链接
    assert "https://qm.qq.com/test" in content
    assert "https://pd.qq.com/test" in content

    # 检查备用链接
    assert "https://quark.test" in content
    assert "https://baidu.test" in content
    assert "https://uc.test" in content
    assert "https://xunlei.test" in content


def test_build_wordpress_payload():
    """测试构造 WordPress payload"""
    candidate = ResourceCandidate(
        canonical_title="流浪地球2",
        year=2023,
        category="电影",
        search_keyword="流浪地球2",
        summary="这是摘要",
        tags=["科幻"]
    )

    payload = build_wordpress_payload(
        candidate=candidate,
        slug="liu-lang-di-qiu-2",
        content_html="<p>测试内容</p>"
    )

    assert payload.title
    assert "流浪地球2" in payload.title
    assert payload.slug == "liu-lang-di-qiu-2"
    assert payload.excerpt == "这是摘要"
    assert payload.content == "<p>测试内容</p>"
    assert payload.status == "publish"
