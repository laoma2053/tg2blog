"""
广告过滤与文本清洗模块。
规则从 config.yaml 加载，修改后重启容器即可生效。
"""
from __future__ import annotations

import re

from .yaml_cfg import filter_cfg


def _compile(cfg: dict) -> tuple:
    keywords = cfg.get("block_keywords") or []
    block_res = [re.compile(p) for p in (cfg.get("block_regex") or [])]
    clean_rules = []
    for rule in cfg.get("clean_rules") or []:
        flags = re.IGNORECASE if "i" in (rule.get("flags") or "") else 0
        clean_rules.append((re.compile(rule["pattern"], flags), rule.get("repl", "")))
    return keywords, block_res, clean_rules


_BLOCK_KEYWORDS, _BLOCK_RES, _CLEAN_RULES = _compile(filter_cfg())


def should_block(text: str) -> str | None:
    """命中黑名单则返回命中原因字符串，否则返回 None。"""
    for r in _BLOCK_RES:
        if r.search(text):
            return f"正则：{r.pattern}"
    for kw in _BLOCK_KEYWORDS:
        if kw in text:
            return f"关键词：{kw}"
    return None


def clean_text(text: str) -> str:
    """按 clean_rules 清洗文本，返回供解析器使用的干净文本。"""
    for pattern, repl in _CLEAN_RULES:
        text = pattern.sub(repl, text)
    return text.strip()
