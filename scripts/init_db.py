"""数据库初始化脚本"""
from app.db.base import engine, Base
from app.db.models import TgMessage, Resource, ResourceLink, Article, GoClickLog
from app.core.logger import logger


def init_db():
    """初始化数据库表"""
    logger.info("🔧 开始创建数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ 数据库表创建完成")


if __name__ == "__main__":
    init_db()
