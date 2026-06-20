"""
广告过滤与文本清洗模块。

should_block()：命中则丢弃整条消息（关键词 + 正则黑名单）。
clean_text()  ：保留消息但清洗推广内容（去链接行、尾部导流等），
               在解析前调用，避免干扰片名/集数提取。
"""
from __future__ import annotations

import re

from .config import Config

# ── 阻断规则（命中即丢弃）────────────────────────────────────────────────────
_BLOCK_RES = [re.compile(p, re.IGNORECASE) for p in [
    r"telegram\.me/",
    r"t\.me/",
]]

# ── 清洗规则（保留消息，删除特定行/片段）────────────────────────────────────
# 按顺序执行，每条为 (compiled_regex, replacement)
_CLEAN_RULES: list[tuple[re.Pattern, str]] = [
    # 删除"链接/阿里/夸克/百度：https://..."整行
    (re.compile(r"(?m)^(?:链接|阿里|夸克|百度)[:：]\s*https?://\S+\s*$"), ""),
    # 删除"📤 资源链接：..."整行
    (re.compile(r"(?m)^📤\s*资源链接[:：].*$"), ""),
    # 删除"🍟 投稿人：..."到字符串末尾（尾部导流块）
    (re.compile(r"(?s)🍟\s*投稿人[：:].*$"), ""),
    # 删除所有剩余 http/https 链接
    (re.compile(r"https?://\S+", re.IGNORECASE), ""),
    # 收尾：清理多余空行（超过2个连续空行压缩为1个）
    (re.compile(r"\n{3,}"), "\n\n"),
]


def should_block(text: str, cfg: Config) -> bool:
    """
    返回 True 表示整条消息应丢弃，不进入 pipeline。
    优先级：正则黑名单 > 关键词黑名单。
    """
    if any(r.search(text) for r in _BLOCK_RES):
        return True
    return any(kw in text for kw in cfg.ad_keywords)


def clean_text(text: str) -> str:
    """
    清洗消息文本：去除推广行、网盘链接、尾部导流信息。
    返回清洗后的文本供解析器使用，原始文本仍存入数据库。
    """
    for pattern, repl in _CLEAN_RULES:
        text = pattern.sub(repl, text)
    return text.strip()
