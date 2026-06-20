"""
配置模块 — 从 .env 文件和环境变量读取所有配置。
启动时自动校验必填项，缺少时抛出带明确说明的错误。
严禁在其他模块中硬编码任何密钥、地址或业务参数。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    tg_api_id: int = Field(..., description="Telegram App API ID，从 my.telegram.org 获取")
    tg_api_hash: str = Field(..., description="Telegram App API Hash")
    # 支持逗号分隔字符串，如 "@Oscar_4Kmovies,@another"
    tg_channels: list[str] = Field(..., description="监听的频道列表")
    session_dir: str = Field(default="/data/session", description="Telethon session 持久化目录")

    # ── Typecho ───────────────────────────────────────────────────────────────
    typecho_xmlrpc_endpoint: str = Field(..., description="Typecho XMLRPC 接口地址")
    typecho_user: str = Field(..., description="Typecho 后台账号")
    typecho_password: str = Field(..., description="Typecho 后台密码")
    typecho_default_category: str = Field(default="影视资源")

    # ── CloudFlare ImgBed ─────────────────────────────────────────────────────
    imgbed_enable: bool = Field(default=True)
    imgbed_base: str = Field(default="")
    # 认证方式二选一：authCode 或 Bearer Token
    imgbed_auth_code: str = Field(default="")
    imgbed_api_token: str = Field(default="")
    imgbed_upload_folder: str = Field(default="tg-movies")
    imgbed_upload_channel: str = Field(default="telegram")

    # ── TMDB ──────────────────────────────────────────────────────────────────
    tmdb_enable: bool = Field(default=True)
    tmdb_api_token: str = Field(default="")
    tmdb_language: str = Field(default="zh-CN")
    tmdb_cache_days: int = Field(default=7, description="TMDB 查询结果缓存天数")
    # 匹配得分低于此阈值时，不采用 TMDB 结果（见 MODULES.md 打分规则）
    tmdb_score_min: int = Field(default=60)

    # ── 网盘导流（所有文章底部统一展示的固定链接，不随影片变化）─────────────────
    netdisk_quark: str = Field(default="", description="夸克网盘固定入口链接")
    netdisk_baidu: str = Field(default="", description="百度网盘固定入口链接")
    netdisk_thunder: str = Field(default="", description="迅雷网盘固定入口链接")
    netdisk_uc: str = Field(default="", description="UC 网盘固定入口链接")
    main_site_url: str = Field(default="https://www.zhuiju.us")

    # ── 飞书通知 ──────────────────────────────────────────────────────────────
    feishu_webhook: str = Field(default="", description="飞书机器人 Webhook URL，不填则禁用通知")
    # 发布成功默认不通知，失败始终通知
    notify_on_success: bool = Field(default=False)

    # ── 广告过滤 ──────────────────────────────────────────────────────────────
    # 消息包含任一关键词，或含 t.me/ 链接，则判定为广告跳过
    ad_keywords: list[str] = Field(default_factory=list, description="广告关键词黑名单，逗号分隔")

    # ── 运行时 ────────────────────────────────────────────────────────────────
    db_path: str = Field(default="/data/db/tg2blog.sqlite")
    log_level: str = Field(default="INFO")
    catchup_hours: int = Field(default=24, description="启动时追溯历史消息的时间窗口（小时）")
    retry_max: int = Field(default=3, description="发布失败最大自动重试次数")
    max_posts_per_minute: int = Field(default=20)

    # ── validators ────────────────────────────────────────────────────────────

    @field_validator("tg_channels", "ad_keywords", mode="before")
    @classmethod
    def _split_csv(cls, v: str | list) -> list[str]:
        """将逗号分隔字符串转换为列表"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v or []

    @model_validator(mode="after")
    def _validate_enabled_services(self) -> "Config":
        """启用的服务必须提供对应的配置项"""
        if self.imgbed_enable:
            if not self.imgbed_base:
                raise ValueError("IMGBED_ENABLE=true 时必须设置 IMGBED_BASE")
            if not (self.imgbed_auth_code or self.imgbed_api_token):
                raise ValueError("ImgBed 需要 IMGBED_AUTH_CODE 或 IMGBED_API_TOKEN 之一")
        if self.tmdb_enable and not self.tmdb_api_token:
            raise ValueError("TMDB_ENABLE=true 时必须设置 TMDB_API_TOKEN")
        return self


@lru_cache(maxsize=1)
def get_config() -> Config:
    """全局单例，首次调用时加载并验证配置"""
    return Config()
