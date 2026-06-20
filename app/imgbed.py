"""
CloudFlare ImgBed 上传模块。
API 文档：https://cfbed.sanyue.de/api/upload.html

上传接口：POST {IMGBED_BASE}/upload
认证方式（二选一）：
  - Query 参数 authCode=xxx
  - 请求头 Authorization: Bearer <API_TOKEN>

响应为数组，取第一个元素：
  - src       : 文件路径（如 /file/abc123.jpg）；returnFormat=full 时为完整链接
  - publicUrl : 配置了默认 URL 前缀时返回，优先使用
"""
from __future__ import annotations

import logging

import aiohttp

from .config import Config

logger = logging.getLogger(__name__)


class ImgBedError(Exception):
    """图床上传失败，供 pipeline 捕获降级处理"""


async def upload(path: str, cfg: Config) -> str:
    """上传图片，返回可直接用于 <img src> 的完整 URL。"""
    params = _build_params(cfg)
    headers = _build_headers(cfg)

    with open(path, "rb") as f:
        data = aiohttp.FormData()
        # 文件字段名固定为 file，MIME 类型声明为 image/jpeg
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
    """
    构造 Query 参数（参考 API 文档 /api/upload.html）：
      uploadChannel  : 存储渠道，与图床后台配置一致
      uploadFolder   : 存储目录，相对路径，留空则上传到根目录
      returnFormat   : full → 响应直接返回完整链接，省去手动拼接
      uploadNameType : short → 使用短 ID 命名，URL 更简洁
      serverCompress : true  → 服务端压缩图片（仅 Telegram 渠道生效）
      autoRetry      : true  → 上传失败自动切换渠道重试
    """
    params: dict = {
        "uploadChannel": cfg.imgbed_upload_channel,
        "uploadFolder":  cfg.imgbed_upload_folder,
        "returnFormat":  "full",        # 直接返回完整 URL
        "uploadNameType": "short",      # 短 ID，节省 URL 长度
        "serverCompress": "true",
        "autoRetry":      "true",
    }
    # authCode 认证：通过 Query 参数传递
    if cfg.imgbed_auth_code:
        params["authCode"] = cfg.imgbed_auth_code
    return params


def _build_headers(cfg: Config) -> dict:
    """API Token 认证：通过 Authorization: Bearer 请求头传递"""
    if cfg.imgbed_api_token:
        return {"Authorization": f"Bearer {cfg.imgbed_api_token}"}
    return {}


def _parse_url(body: dict | list, base: str) -> str:
    """
    解析上传响应，返回图片完整 URL。
    响应为数组时取第一个元素（普通上传固定返回数组）。
    优先级：publicUrl（配置了默认域名时存在）> src（相对路径时拼 base）
    """
    if isinstance(body, list):
        body = body[0] if body else {}

    if url := body.get("publicUrl"):
        return url

    src = body.get("src", "")
    if src.startswith("/"):
        return f"{base.rstrip('/')}{src}"
    if src:
        return src

    raise ImgBedError(f"响应中无可用 URL: {body}")
