tg2blog 项目交接说明书（交给 Copilot GPT-5.2）
0. 项目目标（必须理解）

本项目是一个 TG → WordPress 自动发文/更新 的流水线服务，用于影视垂直 SEO 获客。

输入：指定 TG 频道（按频道用户名列表）中的消息（new + edit）

处理：解析 TG 文本为结构化字段 → 生成 hash_key 去重/合并 → 渲染固定 HTML 模板

输出：通过 WordPress REST API 自动 创建/更新 文章

导流：文章内 CTA 跳转 zhuiju.us 的搜索页（带 UTM），博客站不放网盘直链

1. 技术栈与部署方式

Python 3.11（Docker 容器化）

Telethon 监听 TG

SQLite（WAL）存储幂等/去重/发布映射

WordPress REST API（Basic Auth + Application Password）

通过 docker-compose 启动单服务容器 tg2blog，并挂载 ./data:/data 保存 session 与 sqlite

关键文件：

app/main.py：启动入口

app/ingest.py：Telethon 监听 new/edit

app/parser.py：TG 文本解析 + hash_key

app/renderer.py：标题/slug/HTML 模板 + content_hash

app/wp_client.py：WP REST create/update

app/pipeline.py：核心业务管道（去重/更新判定/限速/落库）

app/db.py + app/repo.py：SQLite schema + CRUD

2. 环境变量（.env）

项目使用 .env（docker-compose 引入），关键变量：

Telegram

TG_API_ID

TG_API_HASH

TG_CHANNELS=@xxx,@yyy（频道用户名列表，逗号分隔）

SESSION_DIR=/data/session（Telethon session 持久化目录）

DB_PATH=/data/db/tg2blog.sqlite

WordPress

WP_BASE=https://blog.zhuiju.us

WP_USER=tgposter

WP_APP_PWD=xxxx xxxx xxxx xxxx（Application Password，发送请求前会 remove spaces）

WP_VERIFY_TLS=true

导流主站

ZHUIJU_BASE=https://www.zhuiju.us

运行

LOG_LEVEL=INFO

MAX_POSTS_PER_MINUTE=20（pipeline 内 rate limiter）

3. 运行方式（开发/生产）
启动
docker compose up -d --build
docker logs -f tg2blog
重要：首次 Telethon 登录

第一次运行会需要 TG 验证码/可能需要 2FA（Telethon client.start()）。
如果容器内交互不方便，建议：

先在宿主机（同代码）跑一次生成 ./data/session/telethon.session

再启动容器（session 会复用）

4. 数据库结构（SQLite）

app/db.py 会初始化 schema（WAL）：

tg_messages

唯一键：(channel_username, msg_id)

存 raw_text + parsed_json + hash_key，用于回溯与 edit 幂等

content_posts

唯一键：hash_key

存 wp_post_id/wp_url

存 last_episode_num/last_title/last_content_hash

存 status/error_last，便于失败追踪

这两张表保证：

重启不重复发文（幂等）

edit 事件能定位对应 WP 文章进行更新

5. 核心业务逻辑（必须理解）
5.1 解析器（parser.py）

从 TG 文本中提取：

name（片名）、year、episode_num（EPxx）、size_per_ep、tags（#标签）、summary（内容简介）

quality_bucket 目前固定为 4k（用户说明该频道内容都是 4K）

extra_quality 取标题除片名/年份后的描述（如 臻彩/60FPS/杜比/FLAC…）

原则：只提取“确定信息”，缺失字段留空，不编造导演/评分等。

5.2 去重/合并（hash_key）

hash_key = normalize(name) + "_" + year + "_" + quality_bucket
由于都是 4K，实际是“同片名+年份”合并到一篇文章。

用途：

同一剧集 EP24 → EP25（通过 edit 或新贴）会更新同一 WP post

避免重复内容导致 SEO 弱化

5.3 更新判定（pipeline.py）

触发更新的条件：

新渲染的 content_hash 与 DB 不同（title+content sha1）

或 episode_num 增大（强更新信号）

否则 skip，避免频繁写 WP。

5.4 发布到 WordPress

新建：POST /wp-json/wp/v2/posts（status=publish）

更新：POST /wp-json/wp/v2/posts/{id}
认证：Basic Auth（user + application password）

注意：目前未写入 WP 的 tags/categories（只写在正文里）。需要的话可加“自动创建/匹配 tag_id”逻辑。

5.5 SEO 与导流

文章模板中 CTA 指向：
{ZHUIJU_BASE}/s/<片名>?utm_source=blog&utm_medium=seo&utm_campaign=tg_auto
并加 rel="nofollow"。

博客站不放网盘直链，降低风险，主站承接转化。

6. 已知限制/风险点（接手后优先关注）

Telethon 登录交互：容器第一次启动可能需要输入验证码（建议先在宿主机生成 session）

解析鲁棒性：不同频道可能格式差异，parser 需逐步增强（但保持不编造）

WP 速率与失败重试：目前失败会记录 status=failed，但没有指数退避重试队列（可增强）

slug 非 ASCII：目前用 url quote，WP 会再 sanitize；可以改成“拼音化 slug”（可选）

标签/分类：目前 tags 只出现在正文，未利用 WP taxonomy（可增强 SEO 结构）

消息来源：目前监听 chats=频道用户名列表；若用户名变更，需要同步更新 env

7. 下一步开发任务清单（按优先级）
P0（稳定性/可用性）

 给 WP 发布/更新增加重试机制（指数退避、最多 N 次），失败后保留待重试状态

 增加“无变化更新跳过”的更细策略（已做 content_hash；可再加字段差异日志）

 增加更清晰的日志：CREATE/UPDATE/SKIP + 关键字段（name/year/ep/hash_key/wp_id）

P1（SEO 增强）

 写入 WP tags/categories：

自动创建 tag（POST /wp/v2/tags）并缓存 tag_name→tag_id（SQLite 或内存）

分类：电影/剧集/更新中/完结/题材（可简单做固定映射）

 模板增强：增加“更新时间”“来源频道”“版本信息块”，保持结构化

P1（解析增强）

 更强 EP 解析：支持 “更至 第24集 / 全xx集 / 更新至xx集”

 更强体积解析：支持 “体积：5G/集”“大小：xxGB”

 更强简介截断：正确截断到下一段 marker（现在是粗略 cut_markers）

P2（运营/统计）

 给 CTA 增加更细的 UTM（channel、hash_key、wp_post_id）

 增加简单 metrics：每小时新增/更新/失败数（stdout 或 Prometheus）

8. 验证步骤（接手人自检 checklist）

docker compose up -d --build，日志显示 Telethon started

TG 频道发一条新消息 → WP 自动出现新文章

编辑 TG 原消息（EP24→EP25）→ WP 同文章标题/正文更新

重启容器 → 不重复发文（SKIP 或 UPDATE 判断正确）

SQLite 中 content_posts 有 wp_post_id 与 last_content_hash

9. 需求边界提醒（不要做错方向）

博客站只做 内容获客，不放网盘直链

主站 zhuiju.us 承接转存/变现

解析严格遵循“能确定就写，不能确定就留空 + 兜底文案”，避免错误信息引发投诉与 SEO 质量问题

如果你（Copilot）要开始改代码：建议从 parser.py 的鲁棒性和 wp_client.py/pipeline.py 的重试与 taxonomy（tags/categories）接入开始。