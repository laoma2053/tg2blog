# tg2blog 项目总控开发指令

## 一、项目背景

当前项目是一个自动化影视内容发布系统，核心目标是：

通过监听 Telegram 影视资源频道，把 TG 消息中的影片标题、年份、4K版本信息、更新集数、资源简介、标签、图片等内容自动解析出来，补充 TMDB 影片资料，上传 TG 图片到 CloudFlare-ImgBed 图床，然后自动发布到 Typecho 博客站。

这个 Typecho 站点用于 SEO / GEO 获客，最终导流到主站：

https://www.zhuiju.us

主站 zhuiju.us 是网盘资源搜索与转存变现站，博客站不直接承载网盘资源，只做影视信息整理、资源索引、更新说明和获取入口引导。

当前 Typecho 博客站域名：

https://b.zhuiju.us

---

## 二、项目最终目标

系统最终应形成以下链路：

Telegram 影视频道
→ Python 自动监听
→ 解析 TG 文本与图片
→ 上传 TG 图片到 CloudFlare-ImgBed 图床
→ 调用 TMDB 补全影片资料
→ 生成 SEO/GEO 友好的文章
→ 通过 Typecho XMLRPC 自动发布
→ 文章内引导用户前往 zhuiju.us 获取资源
→ 后续可扩展到 info 条目页、站群、多平台发布

---

## 三、当前优先级

当前不要一次性做完整站群，不要先做复杂 AI 改写。

请先完成 P0 / P1：

### P0：TG → Typecho 自动发文跑通

必须包含：

1. Telethon 监听 TG 频道新消息和编辑消息。
2. 解析 4K 影视 TG 消息格式。
3. 自动生成文章 title、slug、summary、content。
4. 通过 Typecho XMLRPC 发布文章。
5. SQLite 去重，避免重复发布。
6. 支持 TG 消息编辑后更新同一篇 Typecho 文章。

### P1：增强内容质量

在 P0 基础上增加：

1. TG 图片下载。
2. CloudFlare-ImgBed 图床上传。
3. TMDB 影片资料补全。
4. 文章顶部插入图片。
5. 文章正文包含影片信息、版本信息、简介、获取入口、免责声明。
6. Typecho 自动分类。

---

## 四、项目目录建议

请按以下目录结构开发：

```text
tg2typecho/
  app/
    __init__.py
    main.py
    config.py
    ingest.py
    parser.py
    media.py
    imgbed_client.py
    tmdb_client.py
    enrich.py
    renderer.py
    typecho_client.py
    db.py
    repo.py
    pipeline.py
    utils.py
  data/
    db/
    session/
  requirements.txt
  Dockerfile
  docker-compose.yml
  .env.example
  README.md
```

---

## 五、核心模块职责

### 1. config.py

负责读取环境变量。

必须支持：

```env
# Telegram
TG_API_ID=
TG_API_HASH=
TG_CHANNELS=@Oscar_4Kmovies
SESSION_DIR=/data/session

# Typecho
TYPECHO_BASE=https://b.zhuiju.us
TYPECHO_XMLRPC_ENDPOINT=https://b.zhuiju.us/action/xmlrpc
TYPECHO_USER=
TYPECHO_PASSWORD=
TYPECHO_DEFAULT_CATEGORY=影视资源

# 主站导流
ZHUIJU_BASE=https://www.zhuiju.us

# SQLite
DB_PATH=/data/db/tg2typecho.sqlite

# CloudFlare-ImgBed
IMGBED_ENABLE=true
IMGBED_BASE=https://你的图床域名
IMGBED_AUTH_CODE=
IMGBED_API_TOKEN=
IMGBED_UPLOAD_CHANNEL=telegram
IMGBED_CHANNEL_NAME=
IMGBED_UPLOAD_FOLDER=tg-movies
IMGBED_RETURN_FORMAT=full
IMGBED_UPLOAD_NAME_TYPE=short
IMGBED_SERVER_COMPRESS=true
IMGBED_AUTO_RETRY=true

# TMDB
TMDB_ENABLE=true
TMDB_API_TOKEN=
TMDB_LANGUAGE=zh-CN
TMDB_REGION=CN
TMDB_IMAGE_SIZE=w500

# Runtime
LOG_LEVEL=INFO
MAX_POSTS_PER_MINUTE=20
```

注意：

* 所有密钥必须只从环境变量读取。
* 不允许把 Token、密码、API Key 写死在代码里。
* 如果某个增强模块失败，必须允许降级继续发文。

---

### 2. ingest.py

负责 Telegram 监听。

要求：

1. 使用 Telethon。
2. 监听 `events.NewMessage`。
3. 监听 `events.MessageEdited`。
4. 支持频道用户名列表，例如 `@Oscar_4Kmovies,@xxx`。
5. 回调 pipeline 时要传入：

   * channel_username
   * msg_id
   * msg_date
   * raw_text
   * message 对象本身

原因：

message 对象后续用于下载 TG 图片。

---

### 3. parser.py

负责解析 TG 文本。

目标输入示例：

```text
🎬 已更新：太平年（2026）4K 臻彩 MAX+ 60FPS 高码率 杜比环绕声 &FLAC 无损 HiFi 声 更至 EP24

🗂 信息
✦ 体积：5G/ 集
✦ 标签：#太平年 #白宇 #周雨彤 #朱亚文 #倪大红 #剧情 #历史 #古装 #电影

📝 内容简介 
讲述了五代十国时期……
```

必须提取字段：

```python
name              # 太平年
year              # 2026
quality_bucket    # 固定 4k
extra_quality     # 臻彩 MAX+ 60FPS 高码率 杜比 FLAC 等
episode_raw       # EP24
episode_num       # 24
size_per_ep       # 5G/集
tags              # ["太平年", "白宇", "剧情", ...]
summary           # 内容简介
raw_title         # TG 原始标题
hash_key          # 去重用
```

解析原则：

* 只提取确定信息。
* 不要编造导演、评分、地区等字段。
* 解析不到就留空。
* TG 信息优先级高于 TMDB，因为 TG 是资源版本来源。

hash_key 规则：

```text
normalized_name + "_" + year + "_4k"
```

例如：

```text
太平年_2026_4k
```

---

### 4. media.py

负责下载 TG 图片。

要求：

1. 支持 `message.photo`。
2. 支持 document 类型图片。
3. 下载到临时目录，例如 `/tmp/tg2typecho/`。
4. 返回本地文件路径列表。
5. 上传完成后必须清理临时文件。
6. 下载失败不能阻断发文，只记录日志。

图片处理优先级：

```text
TG 图片 > TMDB 海报 > 无图
```

---

### 5. imgbed_client.py

负责上传图片到 CloudFlare-ImgBed。

上传接口：

```text
POST {IMGBED_BASE}/upload
```

要求：

1. 使用 multipart/form-data。
2. 文件字段名默认使用 `file`。
3. 支持两种认证方式：

   * `authCode` query 参数。
   * `Authorization: Bearer <API_TOKEN>`。
4. 支持以下 query 参数：

   * uploadChannel
   * channelName
   * serverCompress
   * autoRetry
   * uploadNameType
   * returnFormat
   * uploadFolder
5. 返回 URL 解析规则：

   * 优先使用 `publicUrl`
   * 其次使用 `src`
   * 如果 `src` 是 `/file/xxx`，则拼接 `IMGBED_BASE + src`
6. 上传失败时抛出异常，但 pipeline 必须捕获，不能阻断发文。

建议函数：

```python
upload_file(path: str) -> str
```

返回最终可用于文章 `<img src="">` 的完整图片 URL。

---

### 6. tmdb_client.py

负责 TMDB API 调用。

要求：

1. 支持 search_tv。
2. 支持 search_movie。
3. 支持 get_tv_detail。
4. 支持 get_movie_detail。
5. 支持 append_to_response=credits,images。
6. 支持 language=zh-CN。
7. 支持构造 poster_url / backdrop_url。
8. 失败不能阻断发文。

TMDB 仅作为补全资料，不允许覆盖 TG 的资源信息。

需要补全字段：

```python
tmdb_id
media_type
tmdb_title
original_title
overview
genres
countries
vote_average
release_date
first_air_date
poster_url
backdrop_url
cast
crew
```

匹配规则：

* 如果 TG 中有 EP、更新至、全xx集等信息，优先查 TV。
* 否则先查 Movie。
* 查不到再切换另一种类型。
* 匹配要打分，低于阈值不要采用。

建议打分：

```text
标题完全匹配 +50
年份匹配 +30
标题包含 +20
media_type 判断正确 +20
```

低于 60 分时，不采用 TMDB 结果。

---

### 7. enrich.py

负责融合 TG 信息和 TMDB 信息。

输入：

```python
ParsedItem
```

输出：

```python
MergedItem
```

融合原则：

1. TG 资源字段最高优先级：

   * 4K
   * EP
   * 杜比
   * FLAC
   * 体积
   * 标签
2. TMDB 只补充：

   * 海报
   * 类型
   * 地区
   * 评分
   * 演员
   * 简介
3. 简介优先级：

   * TMDB overview 如果质量较好则使用。
   * 否则使用 TG summary。
4. TMDB 匹配失败时，直接使用 TG 原始信息生成文章。

---

### 8. renderer.py

负责生成 Typecho 文章标题、slug、正文 HTML。

标题格式：

```text
《片名》年份 4K 更新至EPxx 网盘资源
```

示例：

```text
《太平年》2026 4K 更新至EP24 网盘资源
```

slug 规则：

```text
pinyin-title-year-4k
```

如果暂时不做拼音转换，可以先用 hash slug：

```text
taipingnian-2026-4k
```

如果没有拼音库，不要用中文 URL encode 作为最终 slug，后续要优化成拼音 slug。

正文结构必须包含：

```html
<h2>资源摘要</h2>
<p>《太平年》2026年4K版本，当前更新至EP24，版本包含60FPS、杜比音轨、FLAC无损等信息。</p>

<h2>影片信息</h2>
<ul>
  <li>片名：</li>
  <li>年份：</li>
  <li>类型：</li>
  <li>地区：</li>
  <li>评分：</li>
  <li>主演：</li>
</ul>

<h2>版本信息</h2>
<ul>
  <li>画质：4K</li>
  <li>版本说明：臻彩 MAX+ 60FPS 高码率 杜比 FLAC</li>
  <li>更新状态：EP24</li>
  <li>体积：5G/集</li>
</ul>

<h2>剧情简介</h2>
<p>简介内容</p>

<h2>获取方式</h2>
<p>资源链接可能会变化，请通过站内入口获取最新可用版本：</p>
<p><a href="https://www.zhuiju.us/s/片名?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto" rel="nofollow">点击前往 zhuiju.us 获取资源</a></p>

<h2>常见问题</h2>
<p><strong>Q：这是4K版本吗？</strong><br>A：根据频道发布信息，本资源为4K版本。</p>
<p><strong>Q：更新到第几集？</strong><br>A：当前更新状态以本文显示为准。</p>

<hr>
<p><em>说明：本站仅做影视信息整理与索引展示，不存储任何资源文件。资源获取入口以 zhuiju.us 页面为准。</em></p>
```

如果使用 TMDB 数据，正文底部必须加入：

```text
部分影片资料来自 TMDB。本产品使用 TMDB API，但未经 TMDB 认可或认证。
```

图片渲染规则：

1. 如果 TG 图床图片存在，顶部插入第一张图片。
2. 如果 TG 没图但 TMDB 有 poster_url，插入 TMDB 海报。
3. 多张 TG 图片时：

   * 第一张作为封面图。
   * 其他图片放入“相关图片”区块。
4. img alt 使用：

   * 片名 + 年份 + 4K + 更新状态。

---

### 9. typecho_client.py

负责 Typecho XMLRPC 发布。

Typecho XMLRPC Endpoint 做成配置项：

```env
TYPECHO_XMLRPC_ENDPOINT=https://b.zhuiju.us/action/xmlrpc
```

必须支持：

1. 获取分类。
2. 发布新文章。
3. 更新已有文章。
4. 设置文章标题。
5. 设置文章正文。
6. 设置 slug。
7. 设置分类。
8. 设置标签/关键词。
9. 设置发布时间。
10. 支持 published 状态。

使用 MetaWeblog API 方法：

```text
metaWeblog.newPost
metaWeblog.editPost
metaWeblog.getCategories
```

如果 Typecho 的 XMLRPC 字段名和 WordPress 不完全一致，请以 Typecho 实测结果为准。

不要直接写 Typecho 数据库，除非 XMLRPC 确认不可用。

---

### 10. db.py / repo.py

负责 SQLite 存储。

必须支持：

1. TG 消息去重。
2. hash_key 去重。
3. Typecho cid 记录。
4. 图片 URL 缓存。
5. TMDB 结果缓存。
6. 发文失败记录。
7. 支持消息 edit 更新同一篇文章。

建议表结构：

```sql
CREATE TABLE IF NOT EXISTS tg_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_username TEXT NOT NULL,
  msg_id INTEGER NOT NULL,
  msg_date TEXT,
  raw_text TEXT NOT NULL,
  parsed_json TEXT,
  hash_key TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(channel_username, msg_id)
);

CREATE TABLE IF NOT EXISTS content_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash_key TEXT NOT NULL UNIQUE,
  typecho_cid INTEGER,
  typecho_url TEXT,
  last_episode_num INTEGER,
  last_title TEXT,
  last_content_hash TEXT,
  cover_image_url TEXT,
  tg_image_urls TEXT,
  tmdb_json TEXT,
  status TEXT NOT NULL DEFAULT 'published',
  error_last TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tmdb_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash_key TEXT NOT NULL UNIQUE,
  query TEXT,
  media_type TEXT,
  tmdb_id INTEGER,
  tmdb_json TEXT,
  score INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

去重逻辑：

* 同一个 TG `channel_username + msg_id` 不重复处理。
* 同一个 `hash_key` 对应同一篇 Typecho 文章。
* 如果 EP 从 24 变成 25，更新同一篇文章，而不是新发一篇。
* 如果 content_hash 没变化，跳过更新。

---

### 11. pipeline.py

负责主流程编排。

处理顺序：

```text
收到 TG 消息
  ↓
解析 TG 文本
  ↓
生成 hash_key
  ↓
查询数据库是否已存在
  ↓
如果有历史图片 URL，优先复用，避免重复上传
  ↓
如无历史图片且消息带图，则下载 TG 图片
  ↓
上传图片到 CloudFlare-ImgBed
  ↓
调用 TMDB 补全资料
  ↓
合并 TG + TMDB 字段
  ↓
生成 title / slug / content
  ↓
判断 content_hash
  ↓
新内容：Typecho 新建文章
  ↓
已有文章：Typecho 更新文章
  ↓
写入数据库
```

失败处理：

1. TG 图片下载失败：记录日志，继续发文。
2. ImgBed 上传失败：记录日志，继续使用 TMDB 图。
3. TMDB 失败：记录日志，继续使用 TG 原文。
4. Typecho 发布失败：记录失败状态，保留错误信息，后续可重试。
5. 任何外部 API 都不能导致整个服务崩溃。

---

## 六、自动分类规则

Typecho 后台建议先创建分类：

```text
影视资源
剧集更新
电影资源
4K合集
```

自动分类规则：

```text
如果有 EP / 更新至 / 全xx集 → 剧集更新
如果标签含 电影 → 电影资源
默认 → 影视资源
如果标题含 4K → 同时归入 4K合集（如 XMLRPC 支持多分类）
```

如果 Typecho XMLRPC 不支持多分类，则优先分类：

```text
剧集更新 > 电影资源 > 影视资源
```

---

## 七、标签规则

文章标签来自 TG 的 # 标签。

例如：

```text
#太平年 #白宇 #周雨彤 #剧情 #历史 #古装 #电影
```

转成：

```text
太平年,白宇,周雨彤,剧情,历史,古装,电影,4K
```

不要保留 `#`。

---

## 八、SEO / GEO 要求

每篇文章都必须面向搜索引擎和 AI 可读。

必须做到：

1. 标题清楚。
2. URL 稳定。
3. 正文结构固定。
4. 资源版本信息明确。
5. 获取入口明文展示，不只放按钮。
6. 不要隐藏内容。
7. 不要依赖 JS 才能看到正文。
8. 文章内必须出现 zhuiju.us 的获取入口。
9. 文章不直接放真实网盘资源链接。
10. 文章必须声明“不存储资源文件，仅做信息整理与索引展示”。

获取入口格式：

```text
https://www.zhuiju.us/s/{片名}?utm_source=typecho&utm_medium=seo&utm_campaign=tg_auto
```

后续如果新增 info.zhuiju.us 条目页，再改成：

```text
Typecho文章 → info条目页 → zhuiju.us
```

当前先导流到 zhuiju.us。

---

## 九、Docker 要求

必须提供：

```text
Dockerfile
docker-compose.yml
requirements.txt
.env.example
README.md
```

docker-compose 至少包含：

```yaml
services:
  tg2typecho:
    build: .
    container_name: tg2typecho
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/data
```

Telethon session 必须持久化在：

```text
/data/session
```

SQLite 必须持久化在：

```text
/data/db/tg2typecho.sqlite
```

---

## 十、验收标准

完成后必须满足以下测试：

### 测试 1：基础发布

给定一条 TG 文本消息：

* 能解析片名、年份、EP、标签、简介。
* 能生成 slug。
* 能发布到 Typecho。
* Typecho 后台能看到文章。

### 测试 2：图片发布

TG 消息带图片：

* 能下载图片。
* 能上传到 CloudFlare-ImgBed。
* Typecho 文章顶部能显示图床图片。

### 测试 3：TMDB 补全

TG 标题能匹配 TMDB：

* 文章出现影片信息。
* 文章出现海报或 TG 图片。
* 文章底部出现 TMDB attribution。

### 测试 4：去重

同一条 TG 消息重复处理：

* 不重复发文。

### 测试 5：编辑更新

TG 消息从 EP24 编辑为 EP25：

* 更新同一篇 Typecho 文章。
* 不新建第二篇文章。

### 测试 6：降级

关闭 TMDB 或 ImgBed：

* 系统仍能正常发布纯文本文章。

---

## 十一、禁止事项

开发时不要做以下事情：

1. 不要直接写 Typecho 数据库作为默认方案。
2. 不要把任何 Token、密码、API Key 写死。
3. 不要让 TMDB 覆盖 TG 的资源版本信息。
4. 不要因为图片上传失败导致文章不发布。
5. 不要因为 TMDB 匹配失败导致文章不发布。
6. 不要重复上传同一条消息的图片。
7. 不要重复发布同一资源的文章。
8. 不要改坏当前 Docker 化部署结构。
9. 不要做复杂前端后台，当前只需要命令行日志和 SQLite。
10. 不要一次性引入站群和 AI 改写，先跑通单站自动发布。

---

## 十二、后续扩展方向

当前版本跑通后，后续再扩展：

### P2：硅基流动 AI 改写

* 根据 TG + TMDB 生成更自然的 SEO 内容块。
* 只生成差异化内容块，不要全篇胡编。
* 对 AI 结果做缓存。

### P3：info.zhuiju.us 条目页

* 生成结构化条目页。
* 提供 `/title/{slug}`。
* 提供 `/go/{key}` 跳转 zhuiju.us。
* 主要面向 GEO。

### P4：站群

* 多个 Typecho / WordPress 站点。
* 追更站、影音站、题材站分工。
* 同一 TG 内容生成不同角度文章。
* 发布错峰，避免同一时间同步发。

---

## 十三、当前最重要的交付

请优先完成：

```text
Telethon监听TG
+ parser解析
+ ImgBed图片上传
+ TMDB补全
+ Typecho XMLRPC发布
+ SQLite去重
+ Docker运行
```

请先实现最小可运行版本，再逐步增强。
