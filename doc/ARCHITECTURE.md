# 系统架构设计

## 1. 系统定位

tg2blog 是一个单进程、事件驱动的自动化发布系统，运行于 Docker 容器。
核心目标：监听多个 TG 影视频道 → 解析内容 → 发布至 Typecho → 导流至 zhuiju.us。

---

## 2. 整体数据流

```
TG 影视频道（多个）
    │
    ▼
listen.py  ←── Telethon 实时监听（NewMessage + MessageEdited）
    │            + 启动时 catch-up（补偿最近24小时历史消息）
    │
    ▼
asyncio.Queue  ←── 串行任务队列，防止并发冲突
    │
    ▼
worker.py  ←── 队列消费者（单协程串行处理）
    │
    ├─→ filter.py  ←── 广告过滤（关键词黑名单 + t.me 链接检测）→ 跳过
    │
    ├─→ parse.py   ←── 通用消息解析（提取 name/year/EP/tags/summary/hash_key）
    │
    ├─→ repo.py    ←── 去重检查（channel+msg_id 是否已处理）
    │
    ├─→ fetch.py   ←── 下载 TG 图片（计算 img_hash，临时目录）
    │       │
    │       └─→ imgbed.py  ←── 上传图床，返回 URL（img_hash 相同则复用）
    │
    ├─→ tmdb.py    ←── 查询 TMDB（打分匹配，缓存7天，香港服务器直连）
    │
    ├─→ merge.py   ←── 融合 TG + TMDB（TG 资源字段最高优先级）
    │
    ├─→ render.py  ←── 生成 title / slug（pypinyin）/ HTML 正文
    │
    ├─→ publish.py ←── Typecho XMLRPC（newPost 或 editPost）
    │
    ├─→ repo.py    ←── 写入 SQLite（状态、cid、URL、content_hash）
    │
    └─→ notify.py  ←── 飞书 Webhook（成功可选，失败必发）
```

---

## 3. 进程模型

单 Python 进程，asyncio 事件循环，4 个并发协程：

| 协程 | 职责 | 触发方式 |
|------|------|---------|
| Telethon client | 实时监听 TG 事件，入队 | 事件驱动 |
| queue worker | 串行消费队列，执行 pipeline | 队列驱动 |
| retry scanner | 扫描失败记录，重新入队 | 每 5 分钟定时 |
| catch-up | 启动时追溯24小时历史消息 | 启动一次性 |

---

## 4. 技术栈

| 组件 | 选型 | 关键原因 |
|------|------|---------|
| TG 监听 | Telethon | 用户账号可直接监听频道，Bot API 需要被邀请才能读取 |
| 任务队列 | asyncio.Queue | 单进程串行，天然防并发，无需 Redis/Celery 等额外依赖 |
| 数据存储 | SQLite | 单机部署，零运维，日均百级消息量完全够用 |
| 博客发布 | Typecho XMLRPC | 不直连数据库，兼容 Typecho 1.3.0，升级友好 |
| 图床 | CloudFlare ImgBed | 免费 CDN，稳定可靠 |
| 影片元数据 | TMDB API | 最全中文影视数据；香港服务器可直连 |
| Slug 生成 | pypinyin | SEO 友好的拼音 URL，避免中文编码 |
| 运维告警 | 飞书 Webhook | 无需额外部署，消息推送即时 |
| 容器化 | Docker Compose | 单文件部署，数据目录持久化挂载 |

---

## 5. 并发控制

**根本手段**：asyncio.Queue 串行消费，同一时刻只处理一条消息，不存在同一部影视并发写冲突。

**数据库兜底**：SQLite `UNIQUE` 约束 + `INSERT OR IGNORE`，防止极端情况下的重复插入。

**同一部影视多次消息**（如 EP24 → EP25）：串行队列保证先后顺序，第二条消息到达时第一条已写库，直接走 `editPost` 更新流程。

---

## 6. 降级策略

每个外部依赖独立降级，不影响主流程发文：

| 依赖 | 失败行为 |
|------|---------|
| TG 图片下载 | 跳过图片，继续发文 |
| ImgBed 上传 | 降级用 TMDB 海报；TMDB 也无则无图 |
| TMDB 查询 | 仅用 TG 原文信息发文 |
| Typecho XMLRPC | 记录失败，进入重试队列（最多3次，指数退避） |
| 飞书通知 | 只记日志，不中断主流程 |

---

## 7. 启动序列

```
1. 加载并验证 .env 配置（缺少必要变量则启动失败）
2. 初始化 SQLite（自动建表，幂等）
3. 连接 Typecho XMLRPC，预加载分类列表（内存缓存）
4. 启动 retry scanner 协程
5. 启动 queue worker 协程
6. 连接 Telethon
7. 执行 catch-up（拉取各频道最近24小时内未处理的历史消息，入队）
8. 注册 NewMessage / MessageEdited 事件监听
9. 打印启动完成日志，进入 event loop
```

---

## 8. 目录结构

```
tg2blog/
  app/
    main.py         # 入口，启动序列
    config.py       # 环境变量读取与验证
    listen.py       # TG 监听 + catch-up
    filter.py       # 广告/垃圾消息过滤
    parse.py        # 通用消息解析器
    fetch.py        # TG 图片下载
    imgbed.py       # CloudFlare ImgBed 上传
    tmdb.py         # TMDB API 客户端
    merge.py        # TG + TMDB 数据融合
    render.py       # 文章标题/slug/HTML 生成
    publish.py      # Typecho XMLRPC 客户端
    worker.py       # asyncio 队列消费 + 重试调度
    notify.py       # 飞书 Webhook 通知
    db.py           # SQLite 连接与建表
    repo.py         # 数据访问层
    utils.py        # 公共工具（slug、hash、时间等）
  data/
    db/             # SQLite 文件（容器内 /data/db/）
    session/        # Telethon session（容器内 /data/session/）
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
```
