"""数据库模型定义"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, JSON, Index
from app.db.base import Base


class TgMessage(Base):
    """TG 消息表"""
    __tablename__ = "tg_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    channel_id = Column(String(128), nullable=False)
    channel_name = Column(String(255))
    message_id = Column(String(128), nullable=False)
    message_date = Column(DateTime)
    raw_text = Column(Text)
    raw_image_url = Column(Text)
    raw_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('uk_channel_message', 'channel_id', 'message_id', unique=True),
    )


class Resource(Base):
    """资源表"""
    __tablename__ = "resources"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    canonical_title = Column(String(255), nullable=False)
    alias_title = Column(String(255))
    year = Column(Integer)
    category = Column(String(64))
    search_keyword = Column(String(255), nullable=False)
    description_raw = Column(Text)
    summary = Column(Text)
    cover_image_url = Column(Text)
    status = Column(String(32), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('uk_resource', 'canonical_title', 'year', 'category', unique=True),
    )


class ResourceLink(Base):
    """资源链接表"""
    __tablename__ = "resource_links"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False)
    drive_type = Column(String(32), nullable=False)
    share_id = Column(String(255), nullable=False)
    original_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('uk_drive_share', 'drive_type', 'share_id', unique=True),
    )


class Article(Base):
    """文章表"""
    __tablename__ = "articles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger, nullable=False)
    wp_post_id = Column(BigInteger)
    wp_slug = Column(String(255))
    title_published = Column(String(255))
    published_at = Column(DateTime)
    status = Column(String(32), default='published')
    created_at = Column(DateTime, default=datetime.utcnow)


class GoClickLog(Base):
    """中间页点击日志表"""
    __tablename__ = "go_click_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resource_id = Column(BigInteger)
    article_id = Column(BigInteger)
    search_keyword = Column(String(255))
    referer = Column(Text)
    user_agent = Column(Text)
    ip_hash = Column(String(128))
    created_at = Column(DateTime, default=datetime.utcnow)
