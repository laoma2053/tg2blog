# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

tg2blog 是一个自动化影视内容发布系统：监听 Telegram 影视资源频道 → 解析消息 → 补全 TMDB 数据 → 上传图片到 CloudFlare-ImgBed → 通过 MetaWeblog XMLRPC 发布到 Typecho 博客，最终导流至主站 https://www.zhuiju.us。

目标博客站：https://b.zhuiju.us

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 本地运行（需先复制并填写 .env）
cp .env.example .env
python -m app.main

# Docker 运行
docker-compose up -d

# 查看日志
docker-compose logs -f tg2blog
```

Windows PowerShell 命令分隔用 `;`，不支持 `&&`。

## 配置双轨制

系统配置分两层，职责严格分离：

- `.env` — 敏感密钥和服务地址（`TG_API_ID`/`TYPECHO_*`/`TMDB_API_TOKEN`/`IMGBED_*` 等），通过 `pydantic-settings` 加载，`config.py` 在启动时一次性校验，缺必填项直接退出。
- `config.yaml` — 非敏感业务规则（监听频道列表、过滤关键词、网盘入口链接、TMDB 跳过词等），由 `yaml_cfg.py` 在**模块加载时**读取一次；修改后需重启容器生效，无需改代码或重建镜像。

## 核心数据流

```
listen → [queue] → worker._process:
  1. 消息级去重（tg_messages.channel+msg_id）
  2. 广告过滤（filter.should_block）
  3. 文本清洗（filter.clean_text）
  4. 消息解析（parse.parse → ParsedItem）
  5. 保存消息记录（repo.save_msg）
  6. 查历史发布记录（repo.get_post → content_posts）
  7. 图片处理（fetch → imgbed，img_hash 防重复上传，可降级）
  8. TMDB 查询（带7天缓存，可降级，skip_tmdb 时跳过）
  9. 数据融合（merge.merge → MergedItem）
 10. 文章渲染（render.render → RenderedPost，含 JSON-LD）
 11. content_hash 比对（episode_num+extra_quality+size_per_ep，无变化则跳过发布）
 12. Typecho 发布（MetaWeblog XMLRPC new_post / edit_post）
 13. 保存发布记录（repo.save_post）
```

## 去重与更新机制

**两级去重**，务必区分：

1. **消息级去重**：`tg_messages(channel, msg_id) UNIQUE`，新消息直接跳过；编辑消息（`is_edit=True`）不受此限制，走完整 pipeline。
2. **内容级去重**：`content_hash = MD5(episode_num|extra_quality|size_per_ep)[:16]`，同一影片三字段均未变化则不触发 Typecho 更新，避免无效写入。

**去重键**：`hash_key = normalize(name) + "_" + year + "_4k"`，唯一标识一部影片（跨频道共享）。`normalize` 会去空格并转小写。

**图片去重**：`tg_img_hash` 存上次上传图片的 MD5，新消息图片 MD5 相同则直接复用旧 URL，不重复上传。

## 重试逻辑

只有 Typecho 发布失败才进入重试队列（其他降级不重试）：
- 失败记录写入 `content_posts`，`status=failed`，`next_retry_at` 按指数退避（`2^n` 分钟）递增。
- `retry_loop` 每5分钟扫描到期记录，重新入队时 `message=None`（跳过图片重下载）。
- 超过 `retry_max`（默认3次）进入 `status=dead`，触发飞书告警，停止自动重试。

## 启动序列（main.py）

1. 加载并校验配置（失败则 `sys.exit(1)`）
2. 初始化 SQLite（WAL 模式，幂等建表）
3. 初始化 TypechoClient，预加载分类缓存（失败降级，不退出）
4. 创建无界 `asyncio.Queue`
5. 初始化 Telethon 客户端，`await tg_client.start()`
6. 注册 `NewMessage` / `MessageEdited` 事件处理器
7. 启动后台协程（保存 Task 引用，防止被 GC 回收）：`retry_loop` + `worker.run`
8. 执行启动 catch-up（补偿最近 `catchup_hours` 小时的历史消息）
9. 启动 `reconnect_watcher`（每30秒检测断线，重连时立即触发无时间截止的 catch-up）
10. `await tg_client.run_until_disconnected()` 保持运行

## 关键设计约束

**TG 字段优先级**：`4K/EP/画质/体积/标签` 来自 TG 解析结果（`ParsedItem`），**TMDB 只补充** 海报、评分、演员、简介、类型、地区等元数据，不允许覆盖 TG 资源字段。`merge.py` 中已硬编码此优先级。

**TMDB 打分**：标题完全匹配+50、年份匹配+30、标题包含+20、media_type 正确+20；低于 `tmdb_score_min`（默认60）不采用，但低分结果仍写入 `tmdb_cache` 避免重复低分查询。

**降级原则**：图片下载失败、ImgBed 上传失败、TMDB 匹配失败均**不阻断发文**，只记录日志，走纯文本发布。

**Slug 生成**：`pypinyin` 拼音转写，格式 `{拼音}-{year}-4k`（例：`tai-ping-nian-2026-4k`）。禁止用 URL-encoded 中文作 slug。

**Typecho 协议**：使用 MetaWeblog XMLRPC（`metaWeblog.newPost` / `metaWeblog.editPost`），`xmlrpc.client` 在线程池中执行以避免阻塞 asyncio 事件循环。

**filter.py 初始化时机**：`_BLOCK_KEYWORDS`、`_BLOCK_RES`、`_CLEAN_RULES` 在模块导入时编译，修改 `config.yaml` 中的过滤规则后需重启。

**render.py 输出**：HTML 正文含4段 JSON-LD（BlogPosting / BreadcrumbList / TVSeries|Movie / FAQPage），面向 SEO/GEO 优化，无 JS 依赖，全静态可抓取。

## SQLite 表结构要点

三张表，均通过 `repo.py` 操作（上层禁止直接执行 SQL）：

| 表 | 主键/唯一约束 | 用途 |
|---|---|---|
| `tg_messages` | `UNIQUE(channel, msg_id)` | 消息级去重；存原始文本和解析结果 |
| `content_posts` | `UNIQUE(hash_key)` | 影片级发布状态；追踪 `typecho_cid`、重试状态、`content_hash`、`tg_img_hash` |
| `tmdb_cache` | `UNIQUE(hash_key)` | TMDB 查询缓存，有效期 `tmdb_cache_days`（默认7天） |

## 环境变量（关键）

所有密钥只从 `.env` 读取，参考 `.env.example`。核心变量：

- `TG_API_ID` / `TG_API_HASH`（从 my.telegram.org 获取）
- `TG_CHANNELS`（已迁移至 `config.yaml` `channels` 字段）
- `TYPECHO_XMLRPC_ENDPOINT` / `TYPECHO_USER` / `TYPECHO_PASSWORD`
- `TMDB_API_TOKEN`（`TMDB_ENABLE=true/false`）
- `IMGBED_BASE` / `IMGBED_AUTH_CODE` 或 `IMGBED_API_TOKEN`（`IMGBED_ENABLE=true/false`）
- `DB_PATH`（默认 `/data/db/tg2blog.sqlite`）/ `SESSION_DIR`（Telethon session 持久化目录）
- `CATCHUP_HOURS`（默认24，启动时追溯历史消息的时间窗口）
- `FEISHU_WEBHOOK`（飞书机器人 URL，不填则禁用所有通知）

## 当前优先级

P0（必须先跑通）：Telethon 监听 → parser → XMLRPC 发布 → SQLite 去重/更新
P1（P0 之后）：TG 图片下载 → ImgBed 上传 → TMDB 补全 → 自动分类

## 验收关键场景

1. 同一 TG 消息重复触发 → 不重复发文（消息级去重）
2. TG 消息 EP 从 24 编辑为 25 → 更新同一篇文章（编辑消息触发 content_hash 变更）
3. 关闭 `TMDB_ENABLE` / `IMGBED_ENABLE` → 系统仍能发布纯文本文章
4. Typecho 发布失败 → 按指数退避重试，超限后触发飞书告警
