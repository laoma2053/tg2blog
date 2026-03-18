"""分类判定器测试"""
import pytest
from app.services.category_detector import detect_category
from app.core.constants import CATEGORY_MOVIE, CATEGORY_TV, CATEGORY_SOFTWARE, CATEGORY_OTHER


def test_detect_movie_by_tags():
    """测试通过标签判断电影"""
    category = detect_category(
        title_raw="大侦探福尔摩斯",
        description_raw=None,
        tags_raw=["动作", "悬疑", "犯罪"]
    )
    assert category == CATEGORY_MOVIE


def test_detect_tv_by_title():
    """测试通过标题判断剧集"""
    category = detect_category(
        title_raw="三体 全24集",
        description_raw=None,
        tags_raw=[]
    )
    assert category == CATEGORY_TV


def test_detect_software_by_title():
    """测试通过标题判断软件"""
    category = detect_category(
        title_raw="Photoshop v2.0 安装包",
        description_raw=None,
        tags_raw=[]
    )
    assert category == CATEGORY_SOFTWARE


def test_detect_other_insufficient_info():
    """测试信息不足返回其他"""
    category = detect_category(
        title_raw="未知资源",
        description_raw=None,
        tags_raw=[]
    )
    assert category == CATEGORY_OTHER
