# tg2blog 第一阶段接口与测试用例清单

## 1. 文档目标

本文件用于定义 `tg2blog` 第一阶段的：

1. 内部模块接口
2. 关键函数签名
3. 输入输出规范
4. 异常处理规范
5. 测试用例范围
6. 验收标准

本文件用于约束 AI 编程助手在实现代码时的细节，避免：

- 接口漂移
- 模块职责混乱
- 测试覆盖不足
- 主流程不可维护

---

## 2. 第一阶段边界重申

### 2.1 本阶段实现范围
- 指定 TG 频道监听
- 固定格式消息解析
- 标题标准化
- 分类判定
- 三层去重
- 资源对象创建
- WordPress 自动发布
- 中间页 URL 构造
- 主流程联调
- 单元测试和基础集成测试

### 2.2 本阶段不实现
- 热度评分
- Tavily
- DeepSeek
- 全网采集
- 历史回填
- 后台管理界面
- 内容增强器
- 多模版分流
- 多租户

---

# 3. 模块分层约束

项目代码必须尽量按下面分层组织。

## 3.1 分层定义

### schemas
负责数据结构定义与校验，不包含业务逻辑。

### parsers
负责把原始消息解析成结构化字段。

### normalizers
负责标准化处理，例如标题清洗、slug 生成。

### services
负责业务逻辑编排。

### db/models
负责 ORM 模型定义。

### collectors
负责外部输入接入，例如 Telegram。

### publishers
如果单独拆出发布器，负责 WordPress 交互。

---

## 3.2 禁止事项

1. 不要在 listener 中写复杂业务逻辑
2. 不要在 parser 中直接访问数据库
3. 不要在 normalizer 中直接调外部 API
4. 不要把 WordPress HTML 模板拼接散落在多个文件里
5. 不要把数据库 session 到处传成全局变量
6. 不要写一个超过 150 行的“万能 service”

---

# 4. 核心数据结构接口

以下是建议的 Python 类型接口。AI 可以微调实现方式，但字段语义不得改变。

---

## 4.1 TelegramIncomingMessage

用于监听器接入后的统一输入对象。

```python
class TelegramIncomingMessage(BaseModel):
    channel_id: str
    channel_name: str | None = None
    message_id: str
    message_date: datetime | None = None
    raw_text: str
    cover_image_url: str | None = None
    raw_json: dict | None = None
```

---

## 4.2 ParsedMessage

```python
class ParsedMessage(BaseModel):
    title_raw: str | None = None
    description_raw: str | None = None
    ali_url: str | None = None
    quark_url: str | None = None
    baidu_url: str | None = None
    uc_url: str | None = None
    xunlei_url: str | None = None
    size_text: str | None = None
    tags_raw: list[str] = []
    cover_image_url: str | None = None
```

---

## 4.3 NormalizedTitle

```python
class NormalizedTitle(BaseModel):
    canonical_title: str
    alias_title: str | None = None
    year: int | None = None
    search_keyword: str
```

---

## 4.4 ResourceCandidate

```python
class ResourceCandidate(BaseModel):
    canonical_title: str
    alias_title: str | None = None
    year: int | None = None
    category: str
    search_keyword: str
    description_raw: str | None = None
    summary: str
    cover_image_url: str | None = None
    size_text: str | None = None
    tags: list[str] = []
```

---

## 4.5 ShareFingerprint

```python
class ShareFingerprint(BaseModel):
    drive_type: str
    share_id: str
    original_url: str
```

---

## 4.6 WordPressPostPayload

```python
class WordPressPostPayload(BaseModel):
    title: str
    slug: str
    status: str = "publish"
    excerpt: str
    content: str
    categories: list[int] | list[str] = []
    tags: list[int] | list[str] = []
    featured_media: int | None = None
```

---

## 4.7 ProcessResult

```python
class ProcessResult(BaseModel):
    status: str
    reason: str | None = None
    resource_id: int | None = None
    article_id: int | None = None
    wp_post_id: int | None = None
```

`status` 允许值：

- `skip`
- `merged`
- `published`
- `error`

---

# 5. 核心函数接口定义

---

## 5.1 TG 消息解析器

文件建议：

```text
app/parsers/tg_message_parser.py
```

函数签名：

```python
def parse_tg_message(raw_text: str, cover_image_url: str | None = None) -> ParsedMessage:
    ...
```

### 输入
- `raw_text`: TG 消息文本
- `cover_image_url`: 海报图片 URL

### 输出
- `ParsedMessage`

### 约束
1. 缺字段时不能抛异常
2. 解析失败时返回尽量完整的部分结果
3. `tags_raw` 必须始终是 list
4. `description_raw` 必须尽量完整保留

---

## 5.2 标题标准化器

文件建议：

```text
app/normalizers/title_normalizer.py
```

函数签名：

```python
def normalize_title(title_raw: str) -> NormalizedTitle:
    ...
```

### 输入
- 原始标题字符串

### 输出
- `NormalizedTitle`

### 约束
1. 必须尽量提取年份
2. 必须尽量保留中文主标题
3. `search_keyword` 必须极简
4. 不能把 `canonical_title` 清洗成空字符串
5. 若无法识别英文别名，`alias_title = None`

---

## 5.3 slug 生成器

文件建议：

```text
app/normalizers/slug_builder.py
```

函数签名：

```python
def build_slug(canonical_title: str) -> str:
    ...
```

### 输入
- `canonical_title`

### 输出
- URL 安全 slug

### 约束
1. slug 必须稳定，同一标题多次生成结果一致
2. 尽量短
3. 只包含小写字母、数字、连字符
4. 不得返回空字符串

---

## 5.4 分类判定器

文件建议：

```text
app/services/category_detector.py
```

函数签名：

```python
def detect_category(
    title_raw: str | None,
    description_raw: str | None,
    tags_raw: list[str] | None
) -> str:
    ...
```

### 输出允许值
- `电影`
- `剧集`
- `动漫`
- `综艺`
- `软件`
- `课程`
- `其他`

### 约束
1. 第一阶段规则化实现
2. 缺信息时返回 `其他`
3. 不得抛出未处理异常

---

## 5.5 链接指纹提取器

文件建议：

```text
app/services/dedup_service.py
```

函数签名：

```python
def extract_share_fingerprints(parsed: ParsedMessage) -> list[ShareFingerprint]:
    ...
```

### 约束
1. 只提取存在的链接
2. 去重返回，不重复输出相同 fingerprint
3. 无法提取 `share_id` 时忽略该链接
4. 返回 list，允许为空

---

## 5.6 消息级去重判断

```python
def is_duplicate_message(
    db: Session,
    channel_id: str,
    message_id: str
) -> bool:
    ...
```

---

## 5.7 链接级去重查询

```python
def find_resource_by_share_fingerprints(
    db: Session,
    fingerprints: list[ShareFingerprint]
) -> Resource | None:
    ...
```

---

## 5.8 资源级去重查询

```python
def find_resource_by_resource_key(
    db: Session,
    canonical_title: str,
    year: int | None,
    category: str
) -> Resource | None:
    ...
```

---

## 5.9 资源候选对象构造器

文件建议：

```text
app/services/resource_service.py
```

函数签名：

```python
def build_resource_candidate(
    parsed: ParsedMessage,
    normalized: NormalizedTitle,
    category: str
) -> ResourceCandidate:
    ...
```

### 约束
1. `summary` 用规则模板生成
2. `search_keyword` 默认取 `normalized.search_keyword`
3. `description_raw` 必须透传保存
4. `tags` 基于 `tags_raw` 清洗得到

---

## 5.10 资源创建

```python
def create_resource(
    db: Session,
    candidate: ResourceCandidate
) -> Resource:
    ...
```

---

## 5.11 资源链接保存

```python
def save_resource_links(
    db: Session,
    resource_id: int,
    fingerprints: list[ShareFingerprint]
) -> None:
    ...
```

### 约束
1. 已存在的 `(drive_type, share_id)` 不重复插入
2. 不因单条重复导致整个事务崩溃
3. 要记录冲突日志

---

## 5.12 文章标题生成器

文件建议：

```text
app/services/article_service.py
```

函数签名：

```python
def build_post_title(canonical_title: str) -> str:
    ...
```

### 规则
从以下模板中随机或按稳定策略选一个：

- `{资源名} 网盘资源整理`
- `{资源名} 下载资源合集`
- `{资源名} 高清资源获取方式`

### 约束
1. 输出不能为空
2. 必须包含 `canonical_title`

---

## 5.13 summary 生成器

```python
def build_summary(
    canonical_title: str,
    description_raw: str | None = None
) -> str:
    ...
```

### 约束
1. 第一阶段只做规则模板
2. 输出长度适中，建议 60~140 字
3. 必须出现 `canonical_title`
4. 要体现“去 zhuiju.us 搜索获取”

---

## 5.14 正文渲染器

```python
def render_post_content(
    candidate: ResourceCandidate,
    slug: str,
    qq_group_url: str,
    qq_channel_url: str,
    backup_quark_url: str,
    backup_baidu_url: str,
    backup_uc_url: str,
    backup_xunlei_url: str,
    go_path_prefix: str = "/go"
) -> str:
    ...
```

### 必须输出的区块
1. 资源简介
2. 剧情简介
3. 资源信息
4. 获取方式
5. 社群入口
6. 备用获取入口

---

## 5.15 WordPress payload 构造器

```python
def build_wordpress_payload(
    candidate: ResourceCandidate,
    slug: str,
    content_html: str
) -> WordPressPostPayload:
    ...
```

---

## 5.16 WordPress 发布器

文件建议：

```text
app/services/wordpress_publisher.py
```

函数签名：

```python
def publish_post(payload: WordPressPostPayload) -> dict:
    ...
```

### 输出
建议至少包含：

```python
{
    "id": 123,
    "slug": "da-zhen-tan-fu-er-mo-si",
    "link": "https://..."
}
```

### 约束
1. 必须设置超时
2. 必须处理 HTTP 错误
3. 必须记录请求失败日志
4. 不要吞异常后静默成功

---

## 5.17 主流程处理函数

文件建议：

```text
app/services/process_message_service.py
```

函数签名：

```python
def process_message(
    db: Session,
    message: TelegramIncomingMessage
) -> ProcessResult:
    ...
```

### 逻辑顺序必须固定
1. 判断重复消息
2. 保存原始消息
3. 解析消息
4. 标题标准化
5. 分类判定
6. 构造资源候选对象
7. 提取链接指纹
8. 链接级去重
9. 资源级去重
10. 创建资源
11. 保存资源链接
12. 构造文章
13. 发布 WordPress
14. 保存文章记录
15. 返回结果

---

# 6. 中间页 / go 跳转接口约定

第一阶段不要求实现完整 Web 服务，但必须统一好接口约定。

---

## 6.1 URL 结构

```text
/go/{slug}
```

示例：

```text
/go/da-zhen-tan-fu-er-mo-si
```

---

## 6.2 解析规则

`slug` 对应文章 / 资源记录，最终找到：

```text
search_keyword = 大侦探福尔摩斯
```

然后跳转：

```text
https://www.zhuiju.us/s/大侦探福尔摩斯.html
```

---

## 6.3 跳转服务接口

文件建议：

```text
app/services/go_redirect_service.py
```

函数签名：

```python
def build_go_url(site_base_url: str, slug: str, go_path_prefix: str = "/go") -> str:
    ...
```

```python
def build_zhuiju_search_url(zhuiju_base_url: str, search_keyword: str) -> str:
    ...
```

### 输出示例

```python
build_go_url("https://example.com", "da-zhen-tan-fu-er-mo-si")
# -> https://example.com/go/da-zhen-tan-fu-er-mo-si
```

```python
build_zhuiju_search_url("https://www.zhuiju.us", "大侦探福尔摩斯")
# -> https://www.zhuiju.us/s/大侦探福尔摩斯.html
```

---

# 7. Repository / 数据访问建议

为了让代码更稳，建议 AI 尽量在 `services` 中调用较薄的一层 repository 或 query helper。

至少建议拆这些查询函数：

- `get_tg_message_by_channel_message()`
- `get_resource_by_unique_key()`
- `get_resource_by_link_fingerprint()`
- `create_tg_message()`
- `create_resource()`
- `create_article()`
- `create_resource_links_bulk()`

如果 AI 不单独建 repository 文件，也要保证 query 逻辑集中，不要散落在多个 service 里。

---

# 8. 异常类型建议

建议 AI 自定义少量业务异常，方便定位问题。

例如：

```python
class ParseError(Exception): ...
class NormalizeError(Exception): ...
class WordPressPublishError(Exception): ...
class InvalidResourceError(Exception): ...
```

注意：

- 去重命中不是异常
- 字段缺失不是异常
- 外部请求失败才考虑抛业务异常

---

# 9. 详细测试用例清单

下面是第一阶段必须覆盖的测试。

---

## 9.1 解析器测试 `tests/test_parser.py`

### 用例 1：标准完整样例
输入为完整 TG 文本，断言：

- `title_raw` 正确
- `description_raw` 正确
- `ali_url` 正确
- `quark_url` 正确
- `size_text` 正确
- `tags_raw == ["动作", "悬疑", "犯罪"]`

### 用例 2：只有夸克，没有阿里
断言：

- `quark_url` 有值
- `ali_url is None`

### 用例 3：没有标签
断言：

- `tags_raw == []`

### 用例 4：没有大小
断言：

- `size_text is None`

### 用例 5：描述后直接接标签，没有网盘链接
断言：
- `description_raw` 截断正确
- 其余链接字段为空

### 用例 6：消息最前面无图片
断言：
- `cover_image_url is None`

### 用例 7：多行描述中包含英文括号、中文标点
断言：
- `description_raw` 不应被错误截断

---

## 9.2 标题标准化测试 `tests/test_normalizer.py`

### 用例 1：中英文混排
输入：

```text
大侦探福尔摩斯 Sherlock Holmes (2009)
```

断言：

- `canonical_title == "大侦探福尔摩斯"`
- `alias_title == "Sherlock Holmes"`
- `year == 2009`
- `search_keyword == "大侦探福尔摩斯"`

### 用例 2：只有中文标题
输入：

```text
流浪地球2 (2023)
```

断言：
- `canonical_title == "流浪地球2"`
- `alias_title is None`
- `year == 2023`

### 用例 3：带噪声词
输入：

```text
流浪地球2 4K 国语中字 夸克网盘
```

断言：
- `search_keyword == "流浪地球2"`

### 用例 4：只有英文标题
输入：

```text
Sherlock Holmes (2009)
```

断言：
- `canonical_title` 不为空
- `year == 2009`

### 用例 5：异常空白字符
输入包含多个空格、制表符  
断言标准化后无异常。

### 用例 6：带书名号
输入：

```text
《三体》 (2023)
```

断言：
- `canonical_title == "三体"`

---

## 9.3 slug 生成测试 `tests/test_slug_builder.py`

### 用例 1：中文标题
输入：

```text
大侦探福尔摩斯
```

断言：
- slug 非空
- 只包含 `a-z0-9-`

### 用例 2：同一输入多次生成一致
断言结果相同。

### 用例 3：标题带空格/特殊字符
断言 slug 合法。

---

## 9.4 分类判定测试 `tests/test_category_detector.py`

### 用例 1：动作/悬疑/犯罪标签
断言：`电影`

### 用例 2：标题含“全24集”
断言：`剧集`

### 用例 3：标题含“v2.0 安装包”
断言：`软件`

### 用例 4：信息不足
断言：`其他`

---

## 9.5 去重测试 `tests/test_dedup.py`

### 用例 1：重复消息
库中已有 `(channel_id, message_id)`，断言重复。

### 用例 2：重复阿里链接
库中已有 `alipan:LqNeerS6idB`，断言命中同一资源。

### 用例 3：重复夸克链接
库中已有 `quark:5284716ccbec`，断言命中。

### 用例 4：重复资源键
已有：
- `canonical_title = 大侦探福尔摩斯`
- `year = 2009`
- `category = 电影`

新消息标准化结果相同，断言命中。

### 用例 5：同名不同年份
例如：
- `三体 2023`
- `三体 2008`

断言不视为同一资源。

### 用例 6：链接和资源键都未命中
断言新建资源路径成立。

---

## 9.6 资源服务测试 `tests/test_resource_service.py`

### 用例 1：能正确构造 `ResourceCandidate`
断言字段完整。

### 用例 2：`description_raw` 被保留
断言候选对象中存在。

### 用例 3：`summary` 中包含 `canonical_title`
断言成立。

---

## 9.7 文章服务测试 `tests/test_article_service.py`

### 用例 1：标题生成
断言：
- 包含资源名
- 非空

### 用例 2：正文生成
断言正文中必须包含：
- `资源简介`
- `剧情简介`
- `资源信息`
- `获取方式`
- `社群入口`
- `备用获取入口`

### 用例 3：主入口链接
断言正文中有：

```text
/go/{slug}
```

### 用例 4：备用入口
断言 4 个网盘链接都出现。

### 用例 5：QQ 群 / QQ 频道
断言两个链接都出现。

### 用例 6：WordPress payload
断言：
- title 非空
- slug 非空
- content 非空
- excerpt 非空

---

## 9.8 WordPress 发布器测试 `tests/test_wordpress_publisher.py`

建议使用 mock。

### 用例 1：成功发布
mock 返回 201，断言正确解析返回值。

### 用例 2：401 未授权
断言抛出业务异常或明确错误。

### 用例 3：500 服务端错误
断言记录错误并抛异常。

### 用例 4：超时
断言正确处理 timeout。

---

## 9.9 主流程测试 `tests/test_process_message_service.py`

### 用例 1：重复消息
返回：

```python
status == "skip"
reason == "duplicate_message"
```

### 用例 2：链接级归并
返回：

```python
status == "merged"
reason == "duplicate_by_link"
```

### 用例 3：资源级归并
返回：

```python
status == "merged"
reason == "duplicate_by_resource_key"
```

### 用例 4：成功发布
返回：

```python
status == "published"
resource_id is not None
wp_post_id is not None
```

### 用例 5：WordPress 发布失败
返回 `error` 或抛出明确异常，且日志可追踪。

---

# 10. 集成测试建议

第一阶段至少做 1 个轻量集成测试：

输入一条完整 TG 样例消息，mock WordPress 发布成功，断言：

1. 原始消息入库
2. 资源入库
3. 资源链接入库
4. 文章记录入库
5. 返回 `published`

---

# 11. HTML 正文验证规则

AI 生成 HTML 时，必须保证：

1. 不出现未转义的 `None`
2. 缺失字段时不要生成难看的空标签
3. `description_raw` 为空时，可以省略“剧情简介”正文内容或显示占位文案
4. 链接必须是完整 URL 或站内有效相对路径
5. 不允许把 Python dict 直接渲染进正文

---

# 12. 日志验证清单

关键步骤需要明确日志。测试中不一定逐条断言，但代码中必须存在。

建议日志点：

- `listener.received_message`
- `parser.success`
- `parser.failed`
- `normalizer.success`
- `dedup.duplicate_message`
- `dedup.duplicate_by_link`
- `dedup.duplicate_by_resource_key`
- `resource.created`
- `article.payload_built`
- `wordpress.publish_success`
- `wordpress.publish_failed`
- `process.completed`

---

# 13. AI 编码时的强约束

把这段也可以直接贴给 VSCode 里的模型。

```text
实现代码时请严格遵守以下约束：

1. 严格依据 docs/tg2blog_stage1_prd.md、docs/tg2blog_stage1_spec.md、docs/tg2blog_stage1_interfaces_and_tests.md
2. 先实现最小可运行版本，不要提前加入第二阶段功能
3. 所有代码必须有类型注解
4. 所有公共函数必须有 docstring
5. 所有外部调用必须设置 timeout
6. 必须写 pytest 测试
7. 不要省略 imports
8. 不要只给示例代码，要给可运行的完整代码
9. 不要擅自改变字段名
10. 不要把多个模块职责混在一起
```

---

# 14. 建议的开发指令顺序（最终版）

你到 VSCode 里后，建议按这个顺序推。

## 第一步：建骨架
```text
请严格基于 docs/tg2blog_stage1_prd.md、docs/tg2blog_stage1_spec.md、docs/tg2blog_stage1_interfaces_and_tests.md 初始化项目骨架，并优先实现配置、SQLAlchemy models、Pydantic schemas、requirements.txt、.env.example。输出完整代码。
```

## 第二步：实现解析器
```text
请严格基于三份文档，实现 app/parsers/tg_message_parser.py 与 tests/test_parser.py。输出完整代码，不要只给片段。
```

## 第三步：实现标准化与 slug
```text
请严格基于三份文档，实现：
1. app/normalizers/title_normalizer.py
2. app/normalizers/slug_builder.py
3. tests/test_normalizer.py
4. tests/test_slug_builder.py
输出完整代码。
```

## 第四步：实现分类与去重
```text
请严格基于三份文档，实现：
1. app/services/category_detector.py
2. app/services/dedup_service.py
3. tests/test_category_detector.py
4. tests/test_dedup.py
输出完整代码。
```

## 第五步：实现资源与文章服务
```text
请严格基于三份文档，实现：
1. app/services/resource_service.py
2. app/services/article_service.py
3. tests/test_resource_service.py
4. tests/test_article_service.py
输出完整代码。
```

## 第六步：实现 WordPress 发布器
```text
请严格基于三份文档，实现 app/services/wordpress_publisher.py 与 tests/test_wordpress_publisher.py。要求使用 httpx，具备 timeout、错误处理、日志。
```

## 第七步：实现主流程
```text
请严格基于三份文档，实现 app/services/process_message_service.py 与 tests/test_process_message_service.py。要求严格按照文档中的固定顺序编排流程。
```

## 第八步：实现 Telegram 监听
```text
请严格基于三份文档，实现 app/collectors/telegram_listener.py 和 scripts/run_listener.py。要求使用 Telethon，仅监听白名单频道，仅处理新消息，收到消息后调用 process_message()。
```

## 第九步：补 Docker 与运行说明
```text
请严格基于三份文档，为项目补齐 Dockerfile、docker-compose.yml、scripts/init_db.py，并给出本地运行和测试命令。
```

---

# 15. 最后建议

现在你已经有 3 份文档了：

- `docs/tg2blog_stage1_prd.md`
- `docs/tg2blog_stage1_spec.md`
- `docs/tg2blog_stage1_interfaces_and_tests.md`

这 3 份已经足够让 VSCode 里的 AI 在第一阶段高效率推进。

最关键的做法不是一次性让它“全写完”，而是按我上面的顺序逐步下发。这样它最稳，返工最少。
