# 配置项说明

所有配置均通过 `.env` 文件注入，代码中禁止硬编码任何密钥或地址。
复制 `.env.example` 为 `.env` 后按说明填写。

---

## Telegram

| 变量 | 必填 | 说明 |
|------|------|------|
| `TG_API_ID` | ✅ | Telegram App API ID，从 my.telegram.org 获取 |
| `TG_API_HASH` | ✅ | Telegram App API Hash |
| `TG_CHANNELS` | ✅ | 监听的频道列表，逗号分隔，例：`@Oscar_4Kmovies,@another` |
| `SESSION_DIR` | ✅ | Telethon session 持久化目录，Docker 内固定 `/data/session` |

---

## Typecho

| 变量 | 必填 | 说明 |
|------|------|------|
| `TYPECHO_XMLRPC_ENDPOINT` | ✅ | 例：`https://b.zhuiju.us/action/xmlrpc` |
| `TYPECHO_USER` | ✅ | Typecho 后台账号 |
| `TYPECHO_PASSWORD` | ✅ | Typecho 后台密码 |
| `TYPECHO_DEFAULT_CATEGORY` | ❌ | 默认分类，默认 `影视资源` |

---

## CloudFlare ImgBed

| 变量 | 必填 | 说明 |
|------|------|------|
| `IMGBED_ENABLE` | ❌ | 是否启用图床，默认 `true` |
| `IMGBED_BASE` | 启用时✅ | 图床域名，例：`https://img.example.com` |
| `IMGBED_AUTH_CODE` | 二选一 | authCode 认证方式 |
| `IMGBED_API_TOKEN` | 二选一 | Bearer Token 认证方式 |
| `IMGBED_UPLOAD_FOLDER` | ❌ | 上传目录，默认 `tg-movies` |
| `IMGBED_UPLOAD_CHANNEL` | ❌ | 上传通道，默认 `telegram` |

---

## TMDB

| 变量 | 必填 | 说明 |
|------|------|------|
| `TMDB_ENABLE` | ❌ | 是否启用 TMDB，默认 `true` |
| `TMDB_API_TOKEN` | 启用时✅ | TMDB Read Access Token（Bearer） |
| `TMDB_LANGUAGE` | ❌ | 语言，默认 `zh-CN` |
| `TMDB_CACHE_DAYS` | ❌ | 缓存有效期（天），默认 `7` |
| `TMDB_SCORE_MIN` | ❌ | 最低采用分数，默认 `60` |

---

## 网盘导流（全局固定链接）

所有文章底部统一展示，引导用户前往网盘入口。

| 变量 | 必填 | 说明 |
|------|------|------|
| `NETDISK_QUARK` | ✅ | 夸克网盘固定链接 |
| `NETDISK_BAIDU` | ✅ | 百度网盘固定链接 |
| `NETDISK_THUNDER` | ✅ | 迅雷网盘固定链接 |
| `NETDISK_UC` | ✅ | UC 网盘固定链接 |
| `MAIN_SITE_URL` | ❌ | 主站地址，默认 `https://www.zhuiju.us` |

---

## 飞书通知

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_WEBHOOK` | ❌ | 飞书机器人 Webhook URL；不填则禁用通知 |
| `NOTIFY_ON_SUCCESS` | ❌ | 成功是否通知，默认 `false`；失败始终通知 |

---

## 广告过滤

| 变量 | 必填 | 说明 |
|------|------|------|
| `AD_KEYWORDS` | ❌ | 关键词黑名单，逗号分隔，例：`推广,广告,赞助,加入会员` |

注：`t.me/` 链接检测为内置规则，无需配置。

---

## 运行时

| 变量 | 必填 | 说明 |
|------|------|------|
| `DB_PATH` | ❌ | SQLite 路径，默认 `/data/db/tg2blog.sqlite` |
| `LOG_LEVEL` | ❌ | 日志级别，默认 `INFO` |
| `CATCHUP_HOURS` | ❌ | 启动时补偿历史消息时间窗口（小时），默认 `24` |
| `RETRY_MAX` | ❌ | 最大重试次数，默认 `3` |
| `MAX_POSTS_PER_MINUTE` | ❌ | 发布速率限制，默认 `20` |

---

## .env.example

```env
# Telegram
TG_API_ID=
TG_API_HASH=
TG_CHANNELS=@Oscar_4Kmovies
SESSION_DIR=/data/session

# Typecho
TYPECHO_XMLRPC_ENDPOINT=https://b.zhuiju.us/action/xmlrpc
TYPECHO_USER=
TYPECHO_PASSWORD=
TYPECHO_DEFAULT_CATEGORY=影视资源

# CloudFlare ImgBed
IMGBED_ENABLE=true
IMGBED_BASE=
IMGBED_AUTH_CODE=
IMGBED_API_TOKEN=
IMGBED_UPLOAD_FOLDER=tg-movies

# TMDB
TMDB_ENABLE=true
TMDB_API_TOKEN=
TMDB_LANGUAGE=zh-CN
TMDB_CACHE_DAYS=7
TMDB_SCORE_MIN=60

# 网盘导流
NETDISK_QUARK=
NETDISK_BAIDU=
NETDISK_THUNDER=
NETDISK_UC=
MAIN_SITE_URL=https://www.zhuiju.us

# 飞书通知
FEISHU_WEBHOOK=
NOTIFY_ON_SUCCESS=false

# 广告过滤
AD_KEYWORDS=推广,广告,赞助,加入会员,点击加入,限时优惠

# 运行时
DB_PATH=/data/db/tg2blog.sqlite
LOG_LEVEL=INFO
CATCHUP_HOURS=24
RETRY_MAX=3
MAX_POSTS_PER_MINUTE=20
```
