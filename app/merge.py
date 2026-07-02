"""
数据融合模块 — 合并 TG 解析结果与 TMDB 元数据，生成文章所需的完整数据对象。
TG 资源字段（4K/EP/画质/标签等）优先级最高，TMDB 只填充 TG 没有的元数据。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .parse import ParsedItem
from .tmdb import TMDBResult


@dataclass
class MergedItem:
    # ── TG 来源字段（最高优先级，不被 TMDB 覆盖）────────────────────────────
    name: str
    year: str
    quality_bucket: str
    extra_quality: str
    episode_raw: str
    episode_num: int
    size_per_ep: str
    tags: list[str]
    hash_key: str
    is_series: bool
    raw_title: str
    summary: str             # TG 描述：字段，overview 为空时使用
    type_hint: str           # 前置类型标签推断的分类（如"剧集"/"电影"）

    # ── TMDB 补充字段 ─────────────────────────────────────────────────────────
    tmdb_id: int | None
    media_type: str          # "tv" / "movie"
    overview: str            # 最终简介：TMDB 优先，TG summary 备用
    genres: list[str]
    countries: list[str]
    vote_average: float
    vote_count: int               # TMDB 投票数
    release_date: str
    cast: list[str]
    reviews: list[str]        # TMDB 影评摘要
    poster_url: str
    has_tmdb: bool           # True 时文章底部需加 TMDB attribution

    # ── AI 解析补充字段 ───────────────────────────────────────────────────────
    hdr_type: str            # HDR格式：HDR10 / Dolby Vision / 杜比视界
    encoding: str            # 编码/码率：HQ高码率 / REMUX
    subtitle: str            # 字幕：内嵌简中 / 内嵌繁中 / 外挂字幕
    audio: str               # 音轨：FLAC / DTS / Dolby Atmos / 国语

    # ── 图片（imgbed 上传后的 URL）────────────────────────────────────────────
    cover_image_url: str          # 封面：TG图床图 > TMDB海报 > 空
    extra_image_urls: list[str]   # 其余图片，放入"相关图片"区块


def merge(
    parsed: ParsedItem,
    tmdb: TMDBResult | None,
    image_urls: list[str],
) -> MergedItem:
    """
    融合规则（优先级见 MODULES.md §merge.py）：
    - 封面图：TG 图床图 > TMDB 海报 > 无图
    - 简介：TMDB overview 非空时优先；否则用 TG summary
    """
    cover = image_urls[0] if image_urls else (tmdb.poster_url if tmdb else "")
    extras = image_urls[1:] if len(image_urls) > 1 else []
    overview = (tmdb.overview if tmdb and tmdb.overview else parsed.description) or ""

    return MergedItem(
        # TG 字段
        name=parsed.name,
        year=parsed.year,
        quality_bucket=parsed.quality_bucket,
        extra_quality=parsed.extra_quality,
        episode_raw=parsed.episode_raw,
        episode_num=parsed.episode_num,
        size_per_ep=parsed.size_per_ep,
        tags=parsed.tags,
        hash_key=parsed.hash_key,
        is_series=parsed.is_series,
        raw_title=parsed.raw_title,
        summary=parsed.description,
        type_hint=parsed.type_hint,
        # TMDB 补充
        tmdb_id=tmdb.tmdb_id if tmdb else None,
        media_type=tmdb.media_type if tmdb else ("tv" if parsed.is_series else "movie"),
        overview=overview,
        genres=tmdb.genres if tmdb else [],
        countries=tmdb.countries if tmdb else [],
        vote_average=tmdb.vote_average if tmdb else 0.0,
        vote_count=tmdb.vote_count if tmdb else 0,
        release_date=tmdb.release_date if tmdb else "",
        cast=tmdb.cast if tmdb else [],
        reviews=tmdb.reviews if tmdb else [],
        poster_url=tmdb.poster_url if tmdb else "",
        has_tmdb=tmdb is not None,
        # AI 解析补充字段
        hdr_type=parsed.hdr_type,
        encoding=parsed.encoding,
        subtitle=parsed.subtitle,
        audio=parsed.audio,
        # 图片
        cover_image_url=cover,
        extra_image_urls=extras,
    )
