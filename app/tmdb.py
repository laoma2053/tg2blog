"""
TMDB 客户端模块 — 查询影片元数据（海报、评分、演员、简介等）。
TG 资源字段优先级高于 TMDB，本模块只提供补充数据。
香港服务器可直连，无需代理。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import aiohttp

from .config import Config
from . import yaml_cfg

logger = logging.getLogger(__name__)

_BASE = "https://api.themoviedb.org/3"
_IMG  = "https://image.tmdb.org/t/p"


@dataclass
class TMDBResult:
    tmdb_id: int
    media_type: str          # "tv" / "movie"
    tmdb_title: str
    original_title: str
    overview: str
    genres: list[str]
    countries: list[str]
    vote_average: float
    release_date: str
    poster_url: str
    backdrop_url: str
    cast: list[str]          # 前5位演员
    reviews: list[str]       # 用户影评摘要
    score: int               # 匹配得分，仅用于筛选，不写入文章


async def search(
    name: str, year: str, is_series: bool, cfg: Config
) -> TMDBResult | None:
    """
    返回匹配度 >= tmdb_score_min 的最佳结果。
    is_series=True 优先搜剧集，否则优先搜电影。
    """
    if not cfg.tmdb_enable or not cfg.tmdb_api_token:
        return None

    # 按优先级尝试两种类型
    types = ["tv", "movie"] if is_series else ["movie", "tv"]
    best: TMDBResult | None = None

    for mtype in types:
        result = await _search_one(name, year, mtype, cfg)
        if result and (best is None or result.score > best.score):
            best = result
        if best and best.score >= cfg.tmdb_score_min:
            break

    if best and best.score >= cfg.tmdb_score_min:
        logger.debug("🎬 TMDB匹配 | 片名=%s 得分=%d type=%s id=%d",
                     name, best.score, best.media_type, best.tmdb_id)
        return best

    logger.debug("🎬 TMDB无匹配 | 片名=%s 最高分=%d（阈值%d）",
                 name, best.score if best else 0, cfg.tmdb_score_min)
    return None


async def _search_one(
    name: str, year: str, mtype: str, cfg: Config
) -> TMDBResult | None:
    params: dict = {"query": name, "language": cfg.tmdb_language}
    if year:
        params["first_air_date_year" if mtype == "tv" else "year"] = year

    data = await _get(f"/search/{mtype}", params, cfg)
    if not data or not data.get("results"):
        return None

    # 只对前5条结果打分
    best_item, best_score = None, 0
    for item in data["results"][:5]:
        s = _score(item, name, year, mtype)
        if s > best_score:
            best_score, best_item = s, item

    if not best_item:
        return None

    detail = await _get(
        f"/{mtype}/{best_item['id']}",
        {"language": cfg.tmdb_language, "append_to_response": "credits,reviews"},
        cfg,
    )
    return _build(detail, mtype, best_score) if detail else None


def _score(item: dict, name: str, year: str, mtype: str) -> int:
    """
    打分规则（见 MODULES.md）：
    标题完全匹配+50 / 年份匹配+30 / 标题包含+20 / 类型推断正确+20
    """
    score = 0
    title    = item.get("name") or item.get("title", "")
    original = item.get("original_name") or item.get("original_title", "")
    idate    = (item.get("first_air_date") or item.get("release_date") or "")[:4]

    if title == name or original == name:
        score += 50
    elif name in title or name in original:
        score += 20

    if year and idate == year:
        score += 30

    # 有 first_air_date 说明是剧集
    if (mtype == "tv") == bool(item.get("first_air_date")):
        score += 20

    return score


def _build(d: dict, mtype: str, score: int) -> TMDBResult:
    poster   = d.get("poster_path") or ""
    backdrop = d.get("backdrop_path") or ""
    cast = [
        p["name"] for p in (d.get("credits", {}).get("cast") or [])[:5]
        if p.get("name")
    ]
    genres    = [g["name"] for g in (d.get("genres") or [])]
    countries = [
        c.get("name") or c.get("iso_3166_1", "")
        for c in (d.get("production_countries") or [])
    ] or list(d.get("origin_country") or [])

    max_n = yaml_cfg.tmdb_max_reviews()
    reviews = [
        r["content"].strip()
        for r in ((d.get("reviews") or {}).get("results") or [])[:max_n]
        if r.get("content")
    ]

    return TMDBResult(
        tmdb_id=d["id"],
        media_type=mtype,
        tmdb_title=d.get("name") or d.get("title", ""),
        original_title=d.get("original_name") or d.get("original_title", ""),
        overview=d.get("overview", ""),
        genres=genres,
        countries=countries,
        vote_average=float(d.get("vote_average") or 0),
        release_date=(d.get("first_air_date") or d.get("release_date") or "")[:10],
        poster_url=f"{_IMG}/w500{poster}" if poster else "",
        backdrop_url=f"{_IMG}/w780{backdrop}" if backdrop else "",
        cast=cast,
        reviews=reviews,
        score=score,
    )


async def _get(endpoint: str, params: dict, cfg: Config) -> dict | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{_BASE}{endpoint}",
                params=params,
                headers={"Authorization": f"Bearer {cfg.tmdb_api_token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return await resp.json() if resp.status == 200 else None
    except Exception as e:
        logger.warning("TMDB API异常 | error=%s", e)
        return None
