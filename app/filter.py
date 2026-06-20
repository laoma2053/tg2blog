"""
广告过滤与文本清洗模块。
规则从项目根目录的 config.yaml 加载，修改后重启容器即可生效。

should_block()：命中即丢弃整条消息。
clean_text()  ：清洗推广内容后交给解析器，原始文本仍入库。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# config.yaml 与 app/ 同级（项目根目录）
_YAML_PATH = Path(__file__).parent.parent / "config.yaml"


def _load() -> dict:
    """加载并编译 config.yaml 中的过滤规则，文件不存在时返回空规则。"""
    if not _YAML_PATH.exists():
        logger.warning("⚠️  config.yaml 不存在，过滤规则为空 | path=%s", _YAML_PATH)
        return {"block_keywords": [], "block_regex": [], "clean_rules": []}
    with _YAML_PATH.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("filter", {})


def _compile(cfg: dict) -> tuple[list[str], list[re.Pattern], list[tuple[re.Pattern, str]]]:
    keywords = cfg.get("block_keywords") or []
    block_res = [re.compile(p) for p in (cfg.get("block_regex") or [])]
    clean_rules = []
    for rule in cfg.get("clean_rules") or []:
        flags = re.IGNORECASE if "i" in (rule.get("flags") or "") else 0
        clean_rules.append((re.compile(rule["pattern"], flags), rule.get("repl", "")))
    return keywords, block_res, clean_rules


# 模块加载时编译一次（重启容器即重新加载）
_cfg = _load()
_BLOCK_KEYWORDS, _BLOCK_RES, _CLEAN_RULES = _compile(_cfg)


def should_block(text: str) -> bool:
    """命中关键词或正则黑名单则返回 True，整条消息丢弃。"""
    if any(r.search(text) for r in _BLOCK_RES):
        return True
    return any(kw in text for kw in _BLOCK_KEYWORDS)


def clean_text(text: str) -> str:
    """按 clean_rules 顺序清洗文本，返回供解析器使用的干净文本。"""
    for pattern, repl in _CLEAN_RULES:
        text = pattern.sub(repl, text)
    return text.strip()
