"""
yaml_cfg.py — config.yaml 的统一读取入口。
所有模块从此处获取非敏感业务配置，模块加载时读取一次，重启容器生效。
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).parent.parent / "config.yaml"


def _load() -> dict:
    if not _YAML_PATH.exists():
        logger.warning("⚠️  config.yaml 不存在 | path=%s", _YAML_PATH)
        return {}
    with _YAML_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_data = _load()


def channels() -> list[str]:
    """监听的 TG 频道列表"""
    return [c for c in (_data.get("channels") or []) if c]


def site_url() -> str:
    """主站地址，用于文章导流链接"""
    return (_data.get("site") or {}).get("main_url", "https://www.zhuiju.us")


def netdisk_links() -> dict[str, str]:
    """网盘固定入口 {quark, baidu, thunder, uc}"""
    return _data.get("netdisk") or {}


def filter_cfg() -> dict:
    """过滤规则配置（block_keywords / block_regex / clean_rules）"""
    return _data.get("filter") or {}
