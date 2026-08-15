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

**本仓库无自动化测试套件**（无 pytest / pyproject.toml / CI）。验证改动的方式：

```bash
# 解析器改动：直接对单条消息文本跑纯函数，无需启动服务
python -c "from app.parse import parse; print(parse(open('msg.txt',encoding='utf-8').read()))"

# 渲染改动：parse → merge → render 串起来看 HTML
python -c "from app.parse import parse; from app.merge import merge; from app.render import render; print(render(merge(parse(TEXT), None, [])).content)"

# 端到端：设 LOG_LEVEL=DEBUG，用较小的 CATCHUP_HOURS 跑一次真实频道
```

注意 `app.config` 在导入时即校验 `.env`，`app.yaml_cfg` / `app.filter` 在导入时即读取 `config.yaml`——跑任何脚本前这两个文件必须就位。

## 配置双轨制

系统配置分两层，职责严格分离：

- `.env` — 敏感密钥和服务地址（`TG_API_ID` / `TYPECHO_*` / `TMDB_API_TOKEN` / `IMGBED_*` / `AI_PARSE_*` 等），通过 `pydantic-settings` 加载，`config.py` 在启动时一次性校验，缺必填项直接退出。
- `config.yaml` — 非敏感业务规则，由 `yaml_cfg.py` 在**模块加载时**读取一次；修改后需重启容器生效，无需改代码或重建镜像（docker-compose 以只读方式挂载该文件）。

`config.yaml` 顶层键：`channels` / `site`（`main_url`、`search_prefix`、`alt_search_label`、`alt_search_prefix`）/ `netdisk`（quark、baidu、thunder、uc）/ `tmdb`（`skip_keywords`、`max_reviews`）/ `filter`（`block_keywords`、`block_regex`、`clean_rules`）。

**README.md 部分内容已过时**：`TG_CHANNELS` 和 `NETDISK_*` 现已移至 `config.yaml`，不再从 `.env` 读取；README 中要求预建的 Typecho 分类名也与代码实际产出不符（见"分类体系"）。以本文件为准。

## 核心数据流

```
listen → [queue] → worker._process:
  1. 消息级去重（tg_messages.channel+msg_id）
  2. 广告过滤（filter.should_block）
  3. 文本清洗（filter.clean_text）
  4. 消息解析（AI 优先 → 正则降级 → ParsedItem）
  5. 查历史发布记录（repo.find_post → content_posts，hash_key/alt_hash_key 双向匹配）
  6. 保存消息记录（repo.save_msg，落库用第5步解析出的最终 key）
  7. content_hash 比对（episode_num+extra_quality+size_per_ep，且记录 status='published' 时才直接返回）
  8. 图片处理（fetch → imgbed，img_hash 防重复上传，可降级）
  9. TMDB 查询（带7天缓存，可降级，skip_tmdb 时跳过）
 10. 数据融合（merge.merge → MergedItem）
 11. 文章渲染（render.render → RenderedPost，含 JSON-LD）
 12. Typecho 发布（MetaWeblog XMLRPC new_post / replace_post，受 max_posts_per_minute 限流）
 13. 保存发布记录（repo.save_post）
```

**content_hash 比对必须在网络调用之前**（第7步）。`merge` 对 `episode_num` /
`extra_quality` / `size_per_ep` 是原样透传，所以用 `ParsedItem` 算出的指纹与融合后
完全一致。放到融合之后再判断，等于每条无变化的编辑消息都白跑一遍图片下载+上传和
TMDB 查询——而编辑消息在影视频道里占比很高。

**单消费者串行队列**（见 `doc/ADR.md` ADR-002）：同一影片短时间内的多条消息若并发处理，会各自判断"文章不存在"从而发出重复文章。串行从根本上消除该竞争，因此**增加并发消费者会破坏去重正确性**。

## 解析双路：AI + 正则

第4步先试 AI（`ai_parse.parse`），返回 `None` 或抛异常则降级到纯正则（`parse.parse`）。两者产出同一个 `ParsedItem`，字段分工是硬约定：

| 来源 | 字段 |
|---|---|
| AI 负责（语义） | `name` `year` `type_hint` `is_series` `episode_num` `episode_raw` `skip_tmdb` `hdr_type` `encoding` `subtitle` `audio` |
| 正则负责（结构化） | `quality_bucket` `extra_quality` `size_per_ep` `tags` `description` `raw_title` |

AI 路径内部**仍会调用 `parse.parse`** 填充正则侧字段，所以正则解析器的改动会同时影响两条路径。

`hdr_type` / `encoding` / `subtitle` / `audio` 在纯正则路径下恒为空——它们只由 AI 填充，渲染时"版本信息"区块会因此少几行，属预期行为。

`ai_parse._extract_json` 需容忍 Qwen3 等模型的 `<think>...</think>` 前缀与 ```json 代码块包裹。换模型只改 `AI_PARSE_MODEL`，不改代码。

**`ParsedItem` 是跨模块契约**：新增字段需同步改动 `parse.py`（dataclass + 提取逻辑）、`ai_parse.py`（system prompt + 构造）、`merge.py`（透传到 `MergedItem`）、`render.py`（渲染）四处。例外是 `alt_hash_key`：它只服务于 worker 的去重查找，不进 `MergedItem`，也不参与渲染。

**AI 与正则会算出不同的 `hash_key`**。两者是各自独立的片名+年份提取器，同一条消息经常产出不同结果，最典型的是年份不带括号时正则的 `_extract_year` 取不到 `year`：

```
"云秀行 2026 4K【更12集】"
  AI   → name=云秀行 year=2026 → 云秀行_2026_4k
  正则 → name=云秀行 2026 year=""  → 云秀行2026__4k
```

AI 只要偶发失败降级一次，`hash_key` 就会在两个值之间切换。因此 `ai_parse` 会把正则侧算出的 key 记入 `alt_hash_key`，worker 用 `repo.find_post` 双向匹配（见下）。**不要把 `hash_key` 改成只由某一条路径生成**——那会让所有存量文章的 key 变化，等于把整站重发一遍。

## 去重与更新机制

**两级去重**，务必区分：

1. **消息级去重**：`tg_messages(channel, msg_id) UNIQUE`，新消息直接跳过；编辑消息（`is_edit=True`）不受此限制，走完整 pipeline。
2. **内容级去重**：`content_hash = MD5(episode_num|extra_quality|size_per_ep)[:16]`，同一影片三字段均未变化则不触发 Typecho 更新，避免无效写入。

**去重键**：`hash_key = normalize(name) + "_" + year + "_4k"`，唯一标识一部影片（跨频道共享）。`normalize` 会去空格并转小写。片名提取规则一旦变化，`hash_key` 随之变化，同一影片会被当作新影片重新发文——改 `parse._extract_name` 或 AI prompt 的 `name` 规则时务必意识到这一点。

**查找走 `repo.find_post(conn, hash_key, alt_hash_key)`，不要直接用 `get_post`**。它按三步匹配，命中即返回：

1. `hash_key = 本次 key` —— 常规命中
2. `alt_hash_key = 本次 key` —— 历史记录由另一条解析路径创建，本次 key 是它的别名
3. `hash_key 或 alt_hash_key = 本次备用键` —— 反向匹配

命中 2/3 时 worker 会**改用历史记录的 `hash_key`** 继续后续流程，从而更新同一行、复用同一个 `typecho_cid`，走更新分支而不是新建。`save_post` 每次都把"另一条路径的 key"写回 `alt_hash_key`（本次为空时保留历史值，避免降级路径抹掉已建立的别名）。绕过这套查找会直接导致 Typecho 重复建文。

**图片去重**：`tg_img_hash` 存上次上传图片的 MD5，新消息图片 MD5 相同则直接复用旧 URL，不重复上传。

## 重试逻辑

只有 Typecho 发布失败才进入重试队列（其他降级不重试）：
- 失败记录写入 `content_posts`，`status=failed`，`next_retry_at` 按指数退避（`2^n` 分钟）递增。
- `retry_loop` 每5分钟扫描到期记录，重新入队时 `message=None`（跳过图片重下载，直接复用 `content_posts` 中的历史 URL）。
- 超过 `retry_max`（默认3次）进入 `status=dead`，触发飞书告警，停止自动重试。

**第 7 步的 content_hash 短路必须带 `status='published'` 条件**。失败记录的
`content_hash` 也可能与本次相同（内容变化后是发布环节才失败的），不加这个条件时重试
会在第 7 步静默返回，走不到发布 → `_handle_failure` 不执行 → `retry_count` 不增长 →
`get_retry_due` 的 `retry_count < retry_max` 恒成立 → `retry_max` 死信兜底永不触发。
症状是「积压=N 恒定不降、每 5 分钟无效回捞一次」，且每轮白烧一次 AI 解析请求。

## 启动序列（main.py）

1. 加载并校验配置（失败则 `sys.exit(1)`）
2. 初始化 SQLite（WAL 模式，幂等建表）
3. 初始化 TypechoClient，预加载分类缓存（失败降级，不退出）
4. 创建无界 `asyncio.Queue`
5. 初始化 Telethon 客户端，`await tg_client.start()`
6. 注册 `NewMessage` / `MessageEdited` 事件处理器
7. 启动后台协程（保存 Task 引用，防止被 GC 回收）：`retry_loop` + `worker.run`
8. 执行启动 catch-up（补偿最近 `catchup_hours` 小时的历史消息）
9. 启动 `reconnect_watcher`（每30秒检测断线，重连时立即触发无时间截止的 catch-up）+ `periodic_catchup`（每 `periodic_catchup_minutes` 分钟无条件 catch-up）
10. `await tg_client.run_until_disconnected()` 保持运行

`catch_up(hours=None)` 与 `catch_up(hours=N)` 语义不同：前者只用 `min_id`（每频道已处理的最大 msg_id）限边界，用于重连补偿；后者额外加时间截止，用于启动。

**补偿为什么是两层**：`reconnect_watcher` 依赖观测到"断开→重连"状态翻转，至少有两类漏检——30 秒轮询间隙内完成的快速重连，以及连接始终正常但服务端不再推送 update（此时 `is_connected()` 全程为 True，任何基于断线检测的方案都失效）。`periodic_catchup` 不判断原因，只保证漏掉的消息最终被捞回，是收敛保证而非特定失效模式的补丁。两者互补：前者快（30秒），后者全（不依赖根因）。

补偿的能力边界：只能捞回 msg_id 大于 `MAX(msg_id)` 的消息。若某条消息解析失败（未写入 `tg_messages`）而其后的消息已入库，边界被推高，中间的空洞永久补不回——解析失败本就是丢弃语义，不算缺陷，但排查"消息丢失"时需知道这一点。

## 关键设计约束

**TG 字段优先级**：`4K/EP/画质/体积/标签` 来自 TG 解析结果（`ParsedItem`），**TMDB 只补充**海报、评分、演员、简介、类型、地区等元数据，不允许覆盖 TG 资源字段。`merge.py` 中已硬编码此优先级。封面图优先级：TG 图床图 > TMDB 海报 > 无图。

**TMDB 打分**：标题完全匹配+50、年份匹配+30、标题包含+20、media_type 正确+20；低于 `tmdb_score_min`（默认60）不采用，但低分结果仍写入 `tmdb_cache` 避免重复低分查询。`is_series` 决定先搜 tv 还是 movie，只对前5条结果打分。

**降级原则**：图片下载失败、ImgBed 上传失败、TMDB 匹配失败、AI 解析失败均**不阻断发文**，只记录日志并走降级路径。唯一阻断的是片名提取失败（`parse` 返回 `None`）和 Typecho 发布失败。

**Slug 生成**：`pypinyin` 拼音转写，格式 `{拼音}-{year}-4k`（例：`tai-ping-nian-2026-4k`）。禁止用 URL-encoded 中文作 slug。

**Typecho 协议**：使用 MetaWeblog XMLRPC（`metaWeblog.newPost` / `blogger.deletePost`），`xmlrpc.client` 在线程池（`run_in_executor`）中执行以避免阻塞 asyncio 事件循环。所有 XMLRPC 异常统一包装为 `PublishError` 供 worker 捕获后进入重试。

**更新文章 = 删旧建新，不用 `editPost`**。Typecho 1.3.0 的 `metaWeblog.editPost` 根本不更新：它把 cid 塞进 `$input` 后直接调 `PostEdit->writePost()`，绕过了 `action()` → `prepare()`，`$this->cid` 从未被填上，于是 `EditTrait::publish()` 里的 `have()` 恒为 false，走 `insert()` 新建。`wp.editPost` / `wp.editPage` / `blogger.editPost` 全部转发到同一条路径，同样无效——这是上游缺陷，**不修改 Typecho 核心 PHP**。因此 `publish.replace_post` 先 `blogger.deletePost` 再 `new_post`：删除会释放旧 slug，新建重新拿到干净的 slug，固定链接不变（已实测）。副作用是 **`typecho_cid` 每次更新都会变**，`content_posts.typecho_cid` 随之刷新；`deletePost` 对不存在的 cid 也返回 true，所以"删成功→建失败"后重试是安全的。排查站上重复文章时，先确认是不是这条链路，再怀疑 `hash_key` 漂移。

**不传 `dateCreated`**：Typecho 把收到的时间戳按服务器本地时区（CST）解释，传 UTC 字符串会让 `created` 恒早 8 小时。省略该字段让 Typecho 自己取当前时间。

**分类体系**：`render._auto_category` 产出 `剧集 / 电影 / 综艺 / 动漫 / 音乐 / 综合` 六选一，优先级为 TG 前置类型标签（`type_hint`）> 标签/标题关键词推断 > `media_type`。这些分类名必须在 Typecho 后台已存在，否则 Typecho 会回落到默认分类。`render._CAT_SLUG` 另维护一份分类→URL slug 映射，仅用于 JSON-LD 面包屑。

**模块加载时初始化**：`filter.py` 的 `_BLOCK_KEYWORDS` / `_BLOCK_RES` / `_CLEAN_RULES` 与 `yaml_cfg.py` 的 `_data` 均在模块导入时求值，修改 `config.yaml` 后必须重启进程。

**render.py 输出**：HTML 正文含4段 JSON-LD（BlogPosting / BreadcrumbList / TVSeries|Movie / FAQPage），面向 SEO/GEO 优化，无 JS 依赖，全静态可抓取。JSON-LD 置于正文**末尾**，避免 Typecho 主题自动截取摘要时把结构化数据带入摘要。文章标题格式为 `已更新：{raw_title} {随机网盘后缀}`——后缀从4个网盘名中随机选取，因此同一篇文章每次更新标题都会变，这是有意为之。

## SQLite 表结构要点

三张表，均通过 `repo.py` 操作（上层禁止直接执行 SQL）：

| 表 | 主键/唯一约束 | 用途 |
|---|---|---|
| `tg_messages` | `UNIQUE(channel, msg_id)` | 消息级去重；存原始文本和解析结果 |
| `content_posts` | `UNIQUE(hash_key)` + `INDEX(alt_hash_key)` | 影片级发布状态；追踪 `typecho_cid`、重试状态、`content_hash`、`tg_img_hash`、`alt_hash_key` |
| `tmdb_cache` | `UNIQUE(hash_key)` | TMDB 查询缓存，有效期 `tmdb_cache_days`（默认7天） |

唯一例外：`worker._latest_raw_msg` 直接查询 `tg_messages`（重试时回捞原始消息）。新增查询请加到 `repo.py`。

## 环境变量（关键）

所有密钥只从 `.env` 读取，参考 `.env.example`。核心变量：

- `TG_API_ID` / `TG_API_HASH`（从 my.telegram.org 获取）
- `TYPECHO_XMLRPC_ENDPOINT` / `TYPECHO_USER` / `TYPECHO_PASSWORD`
- `TMDB_API_TOKEN`（`TMDB_ENABLE=true/false`）
- `IMGBED_BASE` / `IMGBED_AUTH_CODE` 或 `IMGBED_API_TOKEN`（`IMGBED_ENABLE=true/false`）
- `AI_PARSE_ENABLE`（默认 false）/ `AI_PARSE_API_KEY` / `AI_PARSE_BASE_URL`（默认硅基流动）/ `AI_PARSE_MODEL`
- `DB_PATH`（默认 `/data/db/tg2blog.sqlite`）/ `SESSION_DIR`（Telethon session 持久化目录）
- `CATCHUP_HOURS`（默认24，启动时追溯历史消息的时间窗口）
- `FEISHU_WEBHOOK`（飞书机器人 URL，不填则禁用所有通知）
- `MAX_POSTS_PER_MINUTE`（默认20，0=不限流）/ `TYPECHO_TIMEOUT`（默认30秒）——见下节

`config.py` 的 `_validate_enabled_services` 校验联动：启用 ImgBed 必须给 `IMGBED_BASE` 且至少一种认证方式；启用 TMDB 必须给 token。AI 无此校验，Key 缺失时靠运行期降级兜底。

## Typecho 侧的 MySQL 负载

本项目**从不直连 MySQL**（依赖里没有任何 MySQL 驱动），XMLRPC 调用面只有三个方法：
`metaWeblog.getCategories`（启动一次）/ `newPost` / `blogger.deletePost`。查重完全在本地
SQLite 完成，不存在"拉取全部历史文章到内存遍历"这类调用。

因此在 `b_zhuiju_us` 库里抓到的无索引 SQL（`typecho_contents` 按
`type+parent+authorId` 扫全表、`typecho_metas` 按 `type+name` 扫全表）**全部由 Typecho
核心 PHP 在处理 newPost 时自己发出**，客户端改不掉。能做的只有两件事：

1. 补索引 —— DDL、EXPLAIN 对比、回滚语句见 `doc/sql/typecho_index.sql`
2. 降低调用频率 —— `MAX_POSTS_PER_MINUTE` 限流（`publish._RateLimiter`，作用于
   newPost 和 deletePost）+ `find_post` 双向去重减少无谓的 newPost

排查这类问题时，先确认 SQL 的发出方是谁，再决定改哪一层。**不要修改 Typecho 核心
PHP**。

`TYPECHO_TIMEOUT` 给 XMLRPC 加了 socket 超时（标准库默认无超时）。MySQL 打满时单次
发布可能长时间不返回，没有超时会让串行消费协程被永久阻塞，队列随之无界堆积——这条
链路会把"慢"放大成"雪崩"。超时后走正常的 `PublishError` 重试路径。

## 验收关键场景

1. 同一 TG 消息重复触发 → 不重复发文（消息级去重）
2. TG 消息 EP 从 24 编辑为 25 → 站上仍只有一篇、URL 不变（cid 会变，见"更新文章 = 删旧建新"）
3. 关闭 `TMDB_ENABLE` / `IMGBED_ENABLE` / `AI_PARSE_ENABLE` → 系统仍能发布纯文本文章
4. Typecho 发布失败 → 按指数退避重试，超限后触发飞书告警
5. AI 解析成功建文后，下一条消息 AI 失败降级正则（hash_key 变化）→ 仍更新同一篇文章，`content_posts` 不新增行
