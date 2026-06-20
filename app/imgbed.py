"""
CloudFlare ImgBed 上传模块 — 将本地图片上传到图床，返回可直接用于 <img src> 的完整 URL。
支持 authCode 和 Bearer Token 两种认证方式。
上传失败抛出 ImgBedError，由 pipeline 捕获降级处理。
"""
from __future__ import annotations

import logging

import aiohttp

from .config import Config

logger = logging.getLogger(__name__)


class ImgBedError(Exception):
    """图床上传失败，供 pipeline 捕获"""


async def upload(path: str, cfg: Config) -> str:
    """
    上传图片文件到 CloudFlare ImgBed，返回完整图片 URL。
    URL 优先取响应中的 publicUrl，其次拼接 src。
    """
    params = _build_params(cfg)
    headers = _build_headers(cfg)

    with open(path, "rb") as f:
        data = aiohttp.FormData()
        data.add_field("file", f, filename="image.jpg", content_type="image/jpeg")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{cfg.imgbed_base}/upload",
                    data=data,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        raise ImgBedError(f"HTTP {resp.status}")
                    body = await resp.json(content_type=None)
                    url = _parse_url(body, cfg.imgbed_base)
                    logger.debug("☁️  图片上传成功 | url=%s", url)
                    return url
        except ImgBedError:
            raise
        except Exception as e:
            raise ImgBedError(str(e)) from e


def _build_params(cfg: Config) -> dict:
    """构造上传接口 query 参数"""
    params: dict = {
        "uploadChannel": cfg.imgbed_upload_channel,
        "uploadFolder": cfg.imgbed_upload_folder,
        "returnFormat": "full",
        "uploadNameType": "short",
        "serverCompress": "true",
        "autoRetry": "true",
    }
    # authCode 认证方式通过 query 参数传递
    if cfg.imgbed_auth_code:
        params["authCode"] = cfg.imgbed_auth_code
    return params


def _build_headers(cfg: Config) -> dict:
    """构造请求头；Bearer Token 认证方式"""
    if cfg.imgbed_api_token:
        return {"Authorization": f"Bearer {cfg.imgbed_api_token}"}
    return {}


def _parse_url(body: dict | list, base: str) -> str:
    """
    从响应体解析图片 URL。
    响应可能是 dict（单文件）或 list（多文件取第一个）。
    """
    if isinstance(body, list):
        body = body[0] if body else {}

    # 优先使用 publicUrl（完整 CDN 地址）
    if url := body.get("publicUrl"):
        return url

    # 其次使用 src，若为相对路径则拼接 base
    src = body.get("src", "")
    if src.startswith("/"):
        return f"{base.rstrip('/')}{src}"
    if src:
        return src

    raise ImgBedError(f"响应中无可用 URL: {body}")
