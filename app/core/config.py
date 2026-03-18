"""配置模块 - 管理应用配置和环境变量"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    # 数据库配置
    DB_HOST: str = "db"  # Docker 容器内使用服务名
    DB_PORT: int = 3306
    DB_NAME: str = "tg2blog"
    DB_USER: str = "tg2blog"
    DB_PASSWORD: str = "tg2blog123456"

    # Telegram 配置
    TG_API_ID: str
    TG_API_HASH: str
    TG_SESSION_NAME: str = "tg2blog"
    TG_CHANNELS: str  # 逗号分隔的频道列表

    # WordPress 配置
    WP_BASE_URL: str
    WP_USERNAME: str
    WP_APP_PASSWORD: str

    # 站点配置
    SITE_BASE_URL: str
    GO_PATH_PREFIX: str = "/go"

    # 追剧站配置
    ZHUIJU_BASE_URL: str = "https://www.zhuiju.us"

    # 社群入口
    QQ_GROUP_URL: str
    QQ_CHANNEL_URL: str

    # 备用网盘导流链接
    BACKUP_QUARK_URL: str
    BACKUP_BAIDU_URL: str
    BACKUP_UC_URL: str
    BACKUP_XUNLEI_URL: str

    # 重试配置
    RETRY_INTERVAL_MINUTES: int = 30  # 重试间隔（分钟）
    RETRY_BATCH_SIZE: int = 10  # 每次重试的资源数量

    @property
    def database_url(self) -> str:
        """生成数据库连接 URL"""
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"

    @property
    def tg_channels_list(self) -> List[str]:
        """解析 TG 频道列表"""
        return [ch.strip() for ch in self.TG_CHANNELS.split(",") if ch.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
