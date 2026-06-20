# tg2blog 部署文档

自动监听 Telegram 影视频道，发布 SEO/GEO 友好的博客文章，导流至主站。

---

## 环境要求

- Docker 20.10+
- Docker Compose v2+
- 一台可访问 Telegram 的服务器（推荐香港 / 新加坡）
- Telegram 账号（用于监听频道，非 Bot）

---

## 第一步：获取代码

```bash
git clone https://github.com/laoma2053/tg2blog.git
cd tg2blog
```

---

## 第二步：准备配置文件

```bash
cp .env.example .env
```

用任意编辑器打开 `.env`，按下表填写必填项：

### 必填

| 变量 | 获取方式 |
|------|---------|
| `TG_API_ID` | 登录 [my.telegram.org](https://my.telegram.org) → API development tools |
| `TG_API_HASH` | 同上 |
| `TG_CHANNELS` | 频道用户名，多个用英文逗号分隔，例：`@Oscar_4Kmovies,@channel2` |
| `TYPECHO_XMLRPC_ENDPOINT` | 例：`https://b.yourdomain.com/action/xmlrpc` |
| `TYPECHO_USER` | Typecho 后台账号 |
| `TYPECHO_PASSWORD` | Typecho 后台密码 |

### 网盘导流（所有文章底部统一展示）

| 变量 | 说明 |
|------|------|
| `NETDISK_QUARK` | 夸克网盘固定入口链接 |
| `NETDISK_BAIDU` | 百度网盘固定入口链接 |
| `NETDISK_THUNDER` | 迅雷网盘固定入口链接 |
| `NETDISK_UC` | UC 网盘固定入口链接 |

### 可选增强

| 变量 | 说明 |
|------|------|
| `TMDB_API_TOKEN` | [TMDB 官网](https://www.themoviedb.org/settings/api) 申请，免费 |
| `IMGBED_BASE` + `IMGBED_AUTH_CODE` | CloudFlare ImgBed 图床地址和认证码 |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook，用于失败告警 |

---

## 第三步：Telegram 首次认证（必须本地交互执行一次）

Telethon 使用真实 Telegram 账号监听频道，首次运行需要输入手机号和验证码完成登录，session 文件保存后后续无需重复操作。

```bash
# 在服务器上安装依赖
pip install -r requirements.txt

# 创建数据目录
mkdir -p data/db data/session

# 运行一次，按提示输入手机号和验证码
python -m app.main
```

看到 `🚀 服务启动完成` 后按 `Ctrl+C` 停止，session 文件已保存在 `data/session/`。

> 如果服务器无法直接运行 Python，也可以在本地完成认证后将 `data/session/` 目录上传到服务器。

---

## 第四步：Docker 部署

```bash
# 构建并启动（后台运行）
docker-compose up -d --build

# 查看实时日志，确认正常运行
docker-compose logs -f tg2blog
```

正常启动时日志示例：

```
2026-06-20 10:00:00  🔌 Telegram 连接成功
2026-06-20 10:00:01  ⏪ 补偿历史消息 | 频道=@Oscar_4Kmovies 发现=3条
2026-06-20 10:00:05  ✅ 发布成功 | 《太平年》EP24 cid=100
2026-06-20 10:00:06  👂 开始监听 | 频道=@Oscar_4Kmovies
2026-06-20 10:00:06  🚀 服务启动完成 | 监听频道=@Oscar_4Kmovies
```

---

## 日常运维

```bash
# 重启服务
docker-compose restart tg2blog

# 停止服务
docker-compose down

# 只看错误和告警
docker-compose logs tg2blog | grep "❌\|🚨\|💀\|⚠️"

# 查看最近发布记录
docker exec -it tg2blog sqlite3 /data/db/tg2blog.sqlite \
  "SELECT hash_key, status, last_episode_num, updated_at FROM content_posts ORDER BY updated_at DESC LIMIT 20;"

# 查看失败记录
docker exec -it tg2blog sqlite3 /data/db/tg2blog.sqlite \
  "SELECT hash_key, retry_count, error_last FROM content_posts WHERE status IN ('failed','dead');"
```

---

## 数据备份

```bash
# SQLite 文件直接复制即可（服务运行中也安全）
cp ./data/db/tg2blog.sqlite ./backup/tg2blog-$(date +%Y%m%d).sqlite
```

---

## Typecho 前置配置

发布前请确认 Typecho 后台已完成以下设置：

1. **开启 XMLRPC**：后台 → 设置 → 基本 → 开启 XML-RPC 推送
2. **创建分类**：手动创建以下分类（或在 `TYPECHO_DEFAULT_CATEGORY` 中指定已有分类名）
   - `影视资源`（默认）
   - `剧集更新`
   - `电影资源`

---

## 关闭可选模块

若 TMDB 或 ImgBed 暂时不可用，在 `.env` 中设置：

```env
TMDB_ENABLE=false
IMGBED_ENABLE=false
```

重启后系统以纯文本模式正常发布，不影响主流程。

---

## 常见问题

**Q：服务重启后会重复发文吗？**
A：不会。每条消息由 `channel + msg_id` 唯一标识，已处理的消息不再重复处理。

**Q：Telegram 账号会被封吗？**
A：监听公开频道属于正常阅读行为，风险极低。建议不要频繁切换 IP，保持 session 持久化。

**Q：多个频道同时推送消息会冲突吗？**
A：不会。系统使用串行队列，所有频道消息统一排队处理，确保同一影片不会产生重复文章。

**Q：TG 消息编辑后（如更新集数）文章会更新吗？**
A：会。编辑消息触发 `MessageEdited` 事件，系统自动更新同一篇 Typecho 文章。
