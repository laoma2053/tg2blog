"""
广告过滤模块 — 识别并跳过广告/推广消息。
规则1：消息包含配置的关键词黑名单（AD_KEYWORDS）。
规则2：消息包含 t.me/ 链接（外链通常为推广入口）。
两条规则取 OR，任一命中则判定为广告。
"""
from __future__ import annotations

import re

from .config import Config

# t.me 链接检测，兼容 http/https 前缀和纯域名格式
_TME_RE = re.compile(r't\.me/', re.IGNORECASE)


def is_ad(text: str, cfg: Config) -> bool:
    """
    返回 True 表示消息应被跳过。
    worker 收到 True 后记录日志，不进入 pipeline。
    """
    if _TME_RE.search(text):
        return True
    return any(kw in text for kw in cfg.ad_keywords)
