# 模块规格说明

命名原则：简单英文单词，见名知意。

---

## main.py — 入口

```python
async def main() -> None
```
执行启动序列（见 ARCHITECTURE.md §7），不含业务逻辑。

---

## config.py — 配置

```python
class Config:
    # Telegram
    tg_api_id: int
    tg_api_hash: str
    tg_channels: list[str]      # ["@Oscar_4Kmovies", "@xxx"]
    session_dir: str

    # Typecho
    typecho_endpoint: str
    typecho_user: str
    typecho_password: str
    typecho_default_category: str

    # ImgBed
    imgbed_enable: bool
    imgbed_base: str
    imgbed_auth_code: str
    imgbed_api_token: str
    imgbed_upload_folder: str

    # TMDB
    tmdb_enable: bool
    tmdb_api_token: str
    tmdb_language: str           # "zh-CN"

    # 网盘导流（全局固定链接）
    netdisk_quark: str
    netdisk_baidu: str
    netdisk_thunder: str
    netdisk_uc: str
    main_site_url: str           # "https://www.zhuiju.us"

    # 通知
    feishu_webhook: str
    notify_on_success: bool      # 默认 False

    # 过滤
    ad_keywords: list[str]       # 黑名单关键词列表

    # 运行时
    db_path: str
    log_level: str
    catchup_hours: int           # 默认 24
    retry_max: int               # 默认 3

def load() -> Config
    # 读取环境变量，缺少必要变量时抛出 ConfigError 并打印缺失项
```

---

## listen.py — TG 监听

```python
async def start(client: TelegramClient, queue: asyncio.Queue, cfg: Config) -> None
    # 注册 NewMessage + MessageEdited 事件，入队

async def catch_up(client: TelegramClient, queue: asyncio.Queue, cfg: Config) -> None
    # 启动时拉取各频道最近 catchup_hours 内未处理的历史消息，入队

# 入队消息格式
@dataclass
class RawMessage:
    channel: str
    msg_id: int
    msg_date: datetime
    text: str
    is_edit: bool
    message: Any    # Telethon Message 对象，用于下载图片
```

---

## filter.py — 广告过滤

```python
def is_ad(text: str, cfg: Config) -> bool
    # 规则1：text 包含 cfg.ad_keywords 中任一关键词 → True
    # 规则2：text 包含 "t.me/" 链接 → True
    # 两条规则 OR 关系
```

---

## parse.py — 通用消息解析

```python
@dataclass
class ParsedItem:
    name: str               # 片名
    year: str               # 年份，解析不到则 ""
    quality_bucket: str     # 固定 "4k"
    extra_quality: str      # "臻彩 MAX+ 60FPS 杜比 FLAC" 等
    episode_raw: str        # "EP24" / "全24集" / ""
    episode_num: int        # 24 / 0
    size_per_ep: str        # "5G/集" / ""
    tags: list[str]         # TG #标签，去掉 #
    summary: str            # 内容简介
    raw_title: str          # TG 原始标题行
    hash_key: str           # "{name}_{year}_4k"（name 已 normalize）
    is_series: bool         # 有 EP 信息则 True

def parse(text: str) -> ParsedItem | None
    # 两层解析：
    # 第一层：严格正则，匹配主流格式
    # 第二层：宽松正则 fallback，覆盖变体格式
    # 完全无法提取片名时返回 None（整条消息跳过）
```

**hash_key 规范**：
```
normalize(name) + "_" + year + "_4k"
normalize：去全角、去空格、转小写
示例："太平年_2026_4k"
```

---

## fetch.py — 图片下载

```python
@dataclass
class FetchedImage:
    local_path: str
    img_hash: str   # MD5，用于去重判断

async def download(message: Any, tmp_dir: str) -> list[FetchedImage]
    # 支持 message.photo 和 document 类型图片
    # 下载失败不抛出，返回空列表并记录日志
    # 调用方负责清理 tmp_dir
```

---

## imgbed.py — 图床上传

```python
async def upload(path: str, cfg: Config) -> str
    # POST multipart/form-data 到 {imgbed_base}/upload
    # 认证：authCode query 参数 或 Authorization: Bearer token
    # 返回：完整图片 URL（优先 publicUrl，其次拼接 src）
    # 失败时抛出 ImgBedError（pipeline 捕获，降级处理）
```

---

## tmdb.py — TMDB 客户端

```python
@dataclass
class TMDBResult:
    tmdb_id: int
    media_type: str         # "tv" / "movie"
    tmdb_title: str
    original_title: str
    overview: str
    genres: list[str]
    countries: list[str]
    vote_average: float
    release_date: str
    poster_url: str
    backdrop_url: str
    cast: list[str]         # 前5位演员名
    score: int              # 匹配得分

async def search(name: str, year: str, is_series: bool, cfg: Config) -> TMDBResult | None
    # 打分规则：标题完全匹配+50 / 年份匹配+30 / 标题包含+20 / media_type 正确+20
    # 低于 60 分返回 None
    # 结果写入 tmdb_cache（有效期7天）
```

---

## merge.py — 数据融合

```python
@dataclass
class MergedItem:
    # TG 字段（最高优先级，不可被覆盖）
    name: str
    year: str
    quality_bucket: str
    extra_quality: str
    episode_raw: str
    episode_num: int
    size_per_ep: str
    tags: list[str]
    hash_key: str
    is_series: bool
    # TMDB 补充字段（仅在 TG 无对应信息时填入）
    tmdb_id: int | None
    media_type: str
    overview: str           # TMDB 简介优先；TG summary 备用
    genres: list[str]
    countries: list[str]
    vote_average: float
    release_date: str
    cast: list[str]
    # 图片
    cover_image_url: str    # 图床URL > TMDB poster > ""
    extra_image_urls: list[str]
    has_tmdb: bool          # 是否采用了 TMDB 数据（影响底部 attribution）

def merge(parsed: ParsedItem, tmdb: TMDBResult | None, image_urls: list[str]) -> MergedItem
```

---

## render.py — 文章渲染

```python
@dataclass
class RenderedPost:
    title: str      # 《片名》年份 4K 更新至EPxx 网盘资源
    slug: str       # pypinyin 拼音，例：tai-ping-nian-2026-4k
    content: str    # 完整 HTML 正文
    tags: list[str] # TG标签 + "4K"
    category: str   # 自动分类

def render(item: MergedItem, cfg: Config) -> RenderedPost
```

**正文 HTML 固定结构**：
1. 封面图（如有）
2. `<h2>资源摘要</h2>` — 一句话概述
3. `<h2>影片信息</h2>` — 片名/年份/类型/地区/评分/主演
4. `<h2>版本信息</h2>` — 画质/版本说明/更新状态/体积
5. `<h2>剧情简介</h2>`
6. `<h2>获取方式</h2>` — zhuiju.us 搜索入口
7. `<h2>资源获取</h2>` — 4个网盘固定链接
8. `<h2>常见问题</h2>` — SEO/GEO 友好 Q&A
9. 免责声明
10. TMDB attribution（仅 has_tmdb=True 时）

**自动分类规则**：
```
is_series=True              → "剧集更新"
tags 含 "电影"              → "电影资源"
默认                        → "影视资源"
```

**slug 生成**：
```python
pypinyin(name, style=NORMAL) + "-" + year + "-4k"
# 示例：太平年 → tai-ping-nian-2026-4k
# 冲突时追加 -2, -3 后缀（repo 检查唯一性）
```

---

## publish.py — Typecho 发布

```python
class TypechoClient:
    def __init__(self, cfg: Config)
    
    def get_categories(self) -> list[dict]
    
    def new_post(self, post: RenderedPost, publish_time: datetime) -> int
        # 返回 typecho_cid
        # 使用 metaWeblog.newPost
    
    def edit_post(self, cid: int, post: RenderedPost) -> bool
        # 使用 metaWeblog.editPost
```

---

## worker.py — 队列消费 + 重试

```python
async def run(queue: asyncio.Queue, cfg: Config) -> None
    # 串行消费队列，执行完整 pipeline
    # 捕获所有异常，写入 repo，触发 notify

async def retry_loop(cfg: Config) -> None
    # 每5分钟扫描 status='failed' AND retry_count < retry_max AND next_retry_at <= now
    # 将符合条件的记录重新入队
    # 指数退避：next_retry_at = now + 2^retry_count 分钟
```

---

## notify.py — 飞书通知

```python
async def send_success(item: MergedItem, url: str, cfg: Config) -> None
    # cfg.notify_on_success=False 时直接返回

async def send_failure(item: MergedItem | None, error: str, retry_count: int, cfg: Config) -> None
    # 必发，失败不抛出异常

# 飞书消息格式（text 类型）：
# 成功：✅ 发布成功｜《片名》EP25｜b.zhuiju.us/xxx
# 失败：🚨 发布失败｜《片名》｜错误: xxx｜重试: 2/3
# 彻底失败：❌ 已放弃｜《片名》｜已重试3次，转人工处理
```

---

## db.py — 数据库

```python
def get_conn(cfg: Config) -> sqlite3.Connection
def init_schema(conn: sqlite3.Connection) -> None  # 幂等建表
```

---

## repo.py — 数据访问

```python
# TG 消息
def msg_exists(conn, channel: str, msg_id: int) -> bool
def save_msg(conn, msg: RawMessage, parsed: ParsedItem) -> None

# 内容帖子
def get_post(conn, hash_key: str) -> dict | None
def save_post(conn, hash_key: str, cid: int, url: str, episode_num: int,
              content_hash: str, cover_url: str, img_urls: list[str],
              img_hash: str) -> None
def mark_failed(conn, hash_key: str, error: str, retry_count: int, next_retry_at: str) -> None
def get_retry_due(conn, now: str, max_retry: int) -> list[dict]

# TMDB 缓存
def get_tmdb_cache(conn, hash_key: str) -> dict | None   # 过期则返回 None
def save_tmdb_cache(conn, hash_key: str, result: TMDBResult) -> None
```

---

## utils.py — 工具函数

```python
def normalize_name(name: str) -> str        # 去全角/空格/转小写
def make_hash_key(name: str, year: str) -> str
def content_hash(episode_num: int, extra_quality: str, size_per_ep: str) -> str
def to_slug(name: str, year: str) -> str    # pypinyin
def now_iso() -> str                        # UTC ISO8601
```
