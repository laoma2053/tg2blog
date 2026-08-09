"""
AI 解析模块 — 调用兼容 OpenAI 接口的大模型从 TG 消息中提取结构化影片信息。
AI 负责语义字段（片名、类型、集数、字幕等），正则负责结构化字段（画质档位、tags 等）。
失败时返回 None，由 worker 降级到纯正则解析，不影响主流程。
"""
from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from .config import Config
from .parse import ParsedItem
from .parse import parse as regex_parse
from .utils import make_hash_key

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一个影视资源信息提取助手。从 Telegram 频道消息中提取结构化信息，只返回 JSON，不要任何其他内容。

字段说明（所有字段均必须存在，无值填空字符串或对应零值）：
- name: 纯片名，去除年份、画质、集数、字幕、HDR、编码、音轨等所有后缀，只保留影视作品名称
- year: 4位年份字符串，无则空字符串
- type_hint: 内容类型，只能是以下之一：剧集 / 电影 / 综艺 / 动漫 / 音乐 / 综合（无法判断时用综合）
- is_series: 布尔值，是否为连续剧集（有集数或明确是电视剧则 true）
- episode_num: 当前最新集数整数，无则 0；"全集"返回 1
- episode_raw: 原始集数文本，如"更26集"/"EP26"/"S01E26"/"全集"，无则空字符串
- skip_tmdb: 布尔值，短剧/综艺/音乐/合集/纪录片返回 true，否则 false
- hdr_type: HDR 格式，如"HDR10"/"Dolby Vision"/"杜比视界"/"HDR"，无则空字符串
- encoding: 编码/码率描述，如"HQ高码率"/"高码率"/"REMUX"/"高清压制"，无则空字符串
- subtitle: 字幕信息，如"内嵌简中"/"内嵌繁中"/"内嵌双语"/"内封简繁英"/"内封简中"/"外挂字幕"/"无字幕"；内嵌=烧录进画面，内封=封入容器轨道可开关，原文有多语言时完整保留（如"内封简繁英"），无则空字符串
- audio: 音轨格式，如"FLAC"/"DTS"/"Dolby Atmos"/"杜比全景声"/"国语"/"粤语"/"国粤双语"，无则空字符串

示例输入：
云秀行(2026)【更26集】【4K.HQ.高码率】【内嵌简中】

示例输出：
{"name":"云秀行","year":"2026","type_hint":"剧集","is_series":true,"episode_num":26,"episode_raw":"更26集","skip_tmdb":false,"hdr_type":"","encoding":"HQ高码率","subtitle":"内嵌简中","audio":""}"""


# ── 公共入口 ──────────────────────────────────────────────────────────────────

async def parse(text: str, cfg: Config) -> ParsedItem | None:
    """
    AI 解析入口。
    - AI 负责：name / year / type_hint / is_series / episode_num / episode_raw /
               skip_tmdb / hdr_type / encoding / subtitle / audio
    - 正则负责：quality_bucket / size_per_ep / tags / description / raw_title
    失败返回 None，worker 降级到纯正则解析。
    """
    client = AsyncOpenAI(
        api_key=cfg.ai_parse_api_key,
        base_url=cfg.ai_parse_base_url,
    )

    try:
        response = await client.chat.completions.create(
            model=cfg.ai_parse_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _compact(text)},
            ],
            temperature=0.0,
            max_tokens=cfg.ai_parse_max_tokens,
            **_extra_body(cfg.ai_parse_extra_body),
        )
    except Exception as e:
        logger.warning("🤖 AI 解析 API 调用失败 | model=%s error=%s", cfg.ai_parse_model, e)
        return None

    choice = response.choices[0]
    raw = (choice.message.content or "").strip()
    # 推理模型（DeepSeek / Qwen3 thinking 等）把思考过程放在 reasoning_content，
    # 正文被 max_tokens 截断时 content 为空，此时回退到思考内容里再找一次 JSON。
    if not raw:
        raw = (getattr(choice.message, "reasoning_content", None) or "").strip()

    ai_data = _extract_json(raw)
    if not ai_data:
        logger.warning(
            "🤖 AI 解析 JSON 提取失败 | finish_reason=%s completion_tokens=%s raw=%.200s",
            choice.finish_reason,
            getattr(response.usage, "completion_tokens", "?"),
            raw or "<content 与 reasoning_content 均为空>",
        )
        return None

    name = (ai_data.get("name") or "").strip()
    if not name:
        logger.warning("🤖 AI 解析未提取到片名，降级正则")
        return None

    year = (ai_data.get("year") or "").strip()

    # 正则解析补充结构化字段（画质档位、tags、体积、描述、原始标题行）
    regex_result = regex_parse(text)

    return ParsedItem(
        # AI 语义字段
        name=name,
        year=year,
        type_hint=ai_data.get("type_hint") or "",
        is_series=bool(ai_data.get("is_series")),
        episode_num=int(ai_data.get("episode_num") or 0),
        episode_raw=(ai_data.get("episode_raw") or "").strip(),
        skip_tmdb=bool(ai_data.get("skip_tmdb")),
        hdr_type=(ai_data.get("hdr_type") or "").strip(),
        encoding=(ai_data.get("encoding") or "").strip(),
        subtitle=(ai_data.get("subtitle") or "").strip(),
        audio=(ai_data.get("audio") or "").strip(),
        # 正则结构化字段（AI 不处理）
        quality_bucket=regex_result.quality_bucket if regex_result else "hd",
        extra_quality=regex_result.extra_quality if regex_result else "",
        size_per_ep=regex_result.size_per_ep if regex_result else "",
        tags=regex_result.tags if regex_result else [],
        description=regex_result.description if regex_result else "",
        raw_title=regex_result.raw_title if regex_result else _first_nonempty_line(text),
        # 派生字段
        hash_key=make_hash_key(name, year),
    )


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _extra_body(raw: str) -> dict:
    """
    解析 AI_PARSE_EXTRA_BODY，返回可直接展开到 create() 的 kwargs。
    主要用途是关闭推理模型的思考模式（各平台参数名不同，见 .env.example）。
    配置格式错误时告警并忽略，不阻断解析。
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("🤖 AI_PARSE_EXTRA_BODY 不是合法 JSON，已忽略 | error=%s", e)
        return {}
    if not isinstance(data, dict) or not data:
        logger.warning("🤖 AI_PARSE_EXTRA_BODY 必须是非空 JSON 对象，已忽略")
        return {}
    return {"extra_body": data}


# "描述：" 行标志。该段落由正则负责提取，对 AI 无用
_DESC_RE = re.compile(r'^\s*描述\s*[：:]')

# 描述段落的结束标志，与 parse._extract_description 的判断保持一致
_DESC_END_PREFIX = (
    "📁", "🏷", "📢", "#", "名称", "资源标题",
    "链接", "阿里", "夸克", "百度", "迅雷", "体积", "大小",
)


def _compact(text: str, max_chars: int = 500) -> str:
    """
    压缩送给 AI 的文本。

    AI 只负责标题行里的语义字段，"描述：" 整段对它毫无用处，却会显著推高输入
    长度——推理模型常把输入逐字复述进思考过程，导致 max_tokens 全耗在复述上、
    正文返回空（日志表现为 finish_reason=length）。

    description 仍由 regex_parse 从**完整原文**中提取，不受此裁剪影响。
    """
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            skipping = False
            continue
        if _DESC_RE.match(s):
            skipping = True
            continue
        if skipping:
            if s.startswith(_DESC_END_PREFIX):
                skipping = False
            else:
                continue
        kept.append(s)
    return "\n".join(kept)[:max_chars]


def _extract_json(text: str) -> dict | None:
    """
    从模型响应中提取 JSON。
    兼容以下情况：
    - Qwen3 / DeepSeek 思考模式输出的 <think>...</think> 前缀
    - 响应被 max_tokens 截断导致 <think> 未闭合
    - ```json 代码块包裹
    - JSON 前后夹带说明文字
    - 裸 JSON 字符串
    """
    if not text:
        return None
    # 剥离成对的 <think>...</think> 推理块
    text = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
    # 未闭合的 <think>（响应被截断）：只丢标签，保留后续可能存在的 JSON
    text = text.replace('<think>', '').strip()
    # 去除 markdown 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 兜底：扫描首个花括号平衡的对象，容忍模型在 JSON 前后夹带解释文字
        return _first_json_object(text)


def _first_json_object(text: str) -> dict | None:
    """扫描并返回文本中第一个花括号平衡且可解析的 JSON 对象。"""
    start = text.find('{')
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if esc:
                esc = False
            elif c == '\\':
                esc = True
            elif c == '"':
                in_str = not in_str
            elif not in_str:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
        start = text.find('{', start + 1)
    return None


def _first_nonempty_line(text: str) -> str:
    """AI 解析时正则结果为 None 的兜底：取消息第一行作为 raw_title。"""
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s[:80]
    return ""
