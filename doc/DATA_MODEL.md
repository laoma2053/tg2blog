# 数据模型设计

## 表结构

### tg_messages — TG 消息记录

```sql
CREATE TABLE IF NOT EXISTS tg_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT    NOT NULL,
    msg_id          INTEGER NOT NULL,
    msg_date        TEXT,
    raw_text        TEXT    NOT NULL,
    parsed_json     TEXT,               -- ParsedItem 序列化
    hash_key        TEXT,
    is_ad           INTEGER DEFAULT 0,  -- 1=被过滤的广告消息
    updated_at      TEXT    NOT NULL,
    UNIQUE(channel, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_tg_hash ON tg_messages(hash_key);
```

**用途**：消息级去重（channel + msg_id 唯一）；保留完整原始文本便于排查解析问题。

---

### content_posts — 发布记录

```sql
CREATE TABLE IF NOT EXISTS content_posts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_key            TEXT    NOT NULL UNIQUE,
    typecho_cid         INTEGER,
    typecho_url         TEXT,
    last_episode_num    INTEGER DEFAULT 0,
    last_title          TEXT,
    content_hash        TEXT,           -- 基于 episode_num+extra_quality+size_per_ep 的 MD5
    cover_image_url     TEXT,
    extra_image_urls    TEXT,           -- JSON 数组
    tg_img_hash         TEXT,           -- 最近一次上传图片的 MD5，用于去重复上传
    tmdb_json           TEXT,
    status              TEXT    NOT NULL DEFAULT 'published',  -- published / failed / dead
    retry_count         INTEGER DEFAULT 0,
    next_retry_at       TEXT,           -- ISO8601，NULL 表示不需要重试
    error_last          TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_post_status ON content_posts(status, next_retry_at);
```

**status 状态流转**：
```
首次发布成功  → published
发布失败      → failed（retry_count++，设置 next_retry_at）
重试成功      → published（清零 retry_count、next_retry_at）
重试3次仍失败 → dead（停止自动重试，飞书告警）
```

**content_hash 计算**：
```python
md5(f"{episode_num}|{extra_quality}|{size_per_ep}")
```
只有资源本身变化才触发 Typecho 更新，避免无意义写入。

---

### tmdb_cache — TMDB 查询缓存

```sql
CREATE TABLE IF NOT EXISTS tmdb_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash_key    TEXT    NOT NULL UNIQUE,
    query       TEXT,
    media_type  TEXT,
    tmdb_id     INTEGER,
    tmdb_json   TEXT,               -- TMDBResult 序列化
    score       INTEGER,
    expires_at  TEXT    NOT NULL,   -- created_at + 7天
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
```

**缓存策略**：
- 有效期 7 天，过期自动重新查询
- score < 60 的结果也缓存（避免每次都重复低分查询），`tmdb_json = NULL`
- 缓存命中且未过期：直接使用，不请求 TMDB API

---

## 字段约定

| 约定 | 规则 |
|------|------|
| 时间字段 | UTC ISO8601 字符串，例：`2026-06-20T07:00:00Z` |
| JSON 字段 | `json.dumps(..., ensure_ascii=False)` |
| 布尔字段 | INTEGER，0/1 |
| 空值 | 使用 NULL，不用空字符串 |

---

## 关键查询

```sql
-- 重试扫描（worker.py 定时执行）
SELECT * FROM content_posts
WHERE status = 'failed'
  AND retry_count < :max_retry
  AND next_retry_at <= :now;

-- 同一部影视的历史图片（pipeline 决策是否复用）
SELECT cover_image_url, tg_img_hash FROM content_posts
WHERE hash_key = :hash_key AND cover_image_url IS NOT NULL;

-- 启动 catch-up 时查最后处理的 msg_id
SELECT MAX(msg_id) FROM tg_messages WHERE channel = :channel;
```
