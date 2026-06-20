# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

tg2blog 是一个自动化影视内容发布系统：监听 Telegram 影视资源频道 → 解析消息 → 补全 TMDB 数据 → 上传图片到 CloudFlare-ImgBed → 通过 XMLRPC 发布到 Typecho 博客，最终导流至主站 https://www.zhuiju.us。

目标博客站：https://b.zhuiju.us

## 目录结构

```
app/
  config.py    # 配置加载与校验
  utils.py     # 公共工具（slug/hash/时间）
  db.py        # SQLite 建表
  repo.py      # 数据访问层
  filter.py    # 广告过滤
  parse.py     # TG 消息解析
  fetch.py     # TG 图片下载
  imgbed.py    # 图床上传
  tmdb.py      # TMDB 查询
  merge.py     # 数据融合
  render.py    # 文章渲染
  publish.py   # Typecho XMLRPC
  notify.py    # 飞书通知
  worker.py    # 队列消费 + 重试
  listen.py    # TG 监听 + catch-up
  main.py      # 入口
data/
  db/          # SQLite 持久化（/data/db/tg2blog.sqlite）
  session/     # Telethon session 持久化
.env.example
Dockerfile
docker-compose.yml
requirements.txt
doc/           # 完整项目文档
```

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

Windows PowerShell 注意：命令分隔用 `;`，不支持 `&&`。

## 核心架构要点

**数据流**：`listen → parse → worker → [fetch → imgbed] → [tmdb] → merge → render → publish → repo`

**去重键**：`hash_key = normalized_name + "_" + year + "_4k"`，同一个 hash_key 对应唯一一篇 Typecho 文章；TG 消息编辑（EP 更新）触发文章更新而非新建。

**降级原则**：图片下载失败、ImgBed 上传失败、TMDB 匹配失败均不阻断发文，只记录日志。

**TG 优先级**：资源版本字段（4K/EP/杜比/FLAC/体积/标签）来自 TG，TMDB 只补充海报、评分、演员、简介等元数据，不允许覆盖 TG 资源信息。

**TMDB 匹配打分**：标题完全匹配+50、年份匹配+30、标题包含+20、media_type 正确+20；低于 60 分不采用。

**Slug**：优先使用拼音（pypinyin），暂无拼音库时使用短哈希，禁止用 URL-encoded 中文作 slug。

## 环境变量（关键）

所有密钥只从 `.env` 读取，参考 `.env.example`。核心变量：

- `TG_API_ID` / `TG_API_HASH` / `TG_CHANNELS`
- `TYPECHO_XMLRPC_ENDPOINT` / `TYPECHO_USER` / `TYPECHO_PASSWORD`
- `TMDB_API_TOKEN`（`TMDB_ENABLE=true/false`）
- `IMGBED_BASE` / `IMGBED_AUTH_CODE`（`IMGBED_ENABLE=true/false`）
- `DB_PATH` / `SESSION_DIR`

## 当前优先级

P0（必须先跑通）：Telethon 监听 → parser → XMLRPC 发布 → SQLite 去重/更新
P1（P0 之后）：TG 图片下载 → ImgBed 上传 → TMDB 补全 → 自动分类

## 验收关键场景

1. 同一 TG 消息重复触发 → 不重复发文
2. TG 消息 EP 从 24 编辑为 25 → 更新同一篇文章
3. 关闭 TMDB_ENABLE / IMGBED_ENABLE → 系统仍能发布纯文本文章
