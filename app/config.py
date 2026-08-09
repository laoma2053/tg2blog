"""
配置模块 — 从 .env 文件和环境变量读取所有配置。
启动时自动校验必填项，缺少时抛出带明确说明的错误。
严禁在其他模块中硬编码任何密钥、地址或业务参数。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
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
    session_dir: str = Field(default="/data/session", description="Telethon session 持久化目录")

    # ── Typecho ───────────────────────────────────────────────────────────────
    typecho_xmlrpc_endpoint: str = Field(..., description="Typecho XMLRPC 接口地址")
    typecho_user: str = Field(..., description="Typecho 后台账号")
    typecho_password: str = Field(..., description="Typecho 后台密码")
    typecho_default_category: str = Field(default="综合")

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

    # ── 飞书通知 ──────────────────────────────────────────────────────────────
    feishu_webhook: str = Field(default="", description="飞书机器人 Webhook URL，不填则禁用通知")
    # 发布成功默认不通知，失败始终通知
    notify_on_success: bool = Field(default=False)
    # 消息被过滤（黑名单）时是否通知
    notify_on_blocked: bool = Field(default=False)

    # ── AI 解析 ───────────────────────────────────────────────────────────────
    ai_parse_enable: bool = Field(default=False, description="启用 AI 解析，优先于正则；失败时自动降级")
    ai_parse_api_key: str = Field(default="", description="AI 服务 API Key")
    ai_parse_base_url: str = Field(default="https://api.siliconflow.cn/v1", description="兼容 OpenAI 接口的 base_url")
    ai_parse_model: str = Field(default="Pro/deepseek-ai/DeepSeek-R1", description="模型名称，换模型只改此项")
    # 推理模型的思考 token 也计入此额度，过小会导致正文被截断、content 返回空
    ai_parse_max_tokens: int = Field(default=2048, description="AI 解析单次响应的最大 token 数")
    # 透传给模型接口的额外参数（JSON 字符串），主要用于关闭推理模型的思考模式。
    # 各平台参数名不统一，写法见 .env.example；留空则不传。
    ai_parse_extra_body: str = Field(default="", description="额外请求参数，JSON 对象字符串")

    # ── 运行时 ────────────────────────────────────────────────────────────────
    db_path: str = Field(default="/data/db/tg2blog.sqlite")
    log_level: str = Field(default="INFO")
    catchup_hours: int = Field(default=24, description="启动时追溯历史消息的时间窗口（小时）")
    # 定期无条件补偿的间隔。断线检测存在盲区（快速重连、连接正常但不推 update），
    # 此项作为兜底保证漏掉的消息最终被捞回；0 表示禁用。
    periodic_catchup_minutes: int = Field(default=30, description="定期补偿间隔（分钟），0=禁用")
    retry_max: int = Field(default=3, description="发布失败最大自动重试次数")
    max_posts_per_minute: int = Field(default=20)

    # ── validators ────────────────────────────────────────────────────────────

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
