# tg2blog 第一阶段开发任务拆解文档

## 1. 文档用途

本文件用于指导 AI 编程助手在 VSCode 中完成 `tg2blog` 第一阶段开发。  
目标是实现一个 **基于指定 Telegram 频道监听的资源内容自动发布系统**。

本文件优先级高于聊天上下文中的零散表述。  
如果实现细节与本文件冲突，以本文件为准。

---

## 2. 第一阶段范围

### 2.1 必须实现

1. 监听指定 Telegram 频道的新消息
2. 解析固定格式 TG 消息
3. 标准化标题，提取真实资源名
4. 对资源进行去重判断
5. 生成 WordPress 文章数据
6. 发布文章到 WordPress
7. 文章中主入口跳转到中间页
8. 中间页记录点击并 302 跳转到 `www.zhuiju.us`
9. 每篇文章固定插入：
   - 主获取入口
   - QQ 群入口
   - QQ 频道入口
   - 4 个固定网盘导流链接

### 2.2 明确不做

1. 全网采集
2. 热度评分
3. Tavily
4. DeepSeek
5. 搜索次数统计
6. 历史大规模回填
7. 多风格内容生成
8. 自动分流实验

---

## 3. 产品约束

### 3.1 搜索站和内容站必须分离

- `www.zhuiju.us` 是搜索交付站
- WordPress 站是内容站
- 内容站不负责真实资源交付
- 内容站负责导流到 `www.zhuiju.us`

### 3.2 搜索关键词必须极简

`search_keyword` 只能保留真实资源名，不能包含：

- 4K
- 高清
- 国语
- 中字
- 百度
- 夸克
- 阿里
- 网盘
- 完整版
- 全集
- 更新至xx集

示例：

- 正确：`流浪地球2`
- 错误：`流浪地球2 4K 国语中字 夸克`

### 3.3 文章定位

文章是 **资源信息页 / 导流页**，不是下载页。

### 3.4 去重目标

同一个资源不能重复生成多篇文章。  
同一 TG 消息也不能重复处理。

---

## 4. 系统架构

```text
Telegram 指定频道
   ↓
Listener
   ↓
Message Parser
   ↓
Title Normalizer
   ↓
Dedup Service
   ↓
Resource Builder
   ↓
WordPress Publisher
   ↓
Article Page
   ↓
Go Redirect
   ↓
www.zhuiju.us/s/{真实资源名}.html
```

---

## 5. 技术建议

### 5.1 推荐语言
Python 3.11+

### 5.2 推荐核心库
- Telethon：监听 Telegram 频道
- SQLAlchemy：数据库 ORM
- httpx：HTTP 请求
- pydantic：数据模型校验
- python-slugify 或自定义 slug 生成
- pytest：测试
- loguru 或标准 logging：日志

### 5.3 数据库建议
MySQL 或 MariaDB

### 5.4 部署形式
Docker 容器运行

---

## 6. 项目目录结构

建议 AI 按以下结构生成项目：

```text
tg2blog/
├─ app/
│  ├─ core/
│  │  ├─ config.py
│  │  ├─ logger.py
│  │  └─ constants.py
│  ├─ db/
│  │  ├─ base.py
│  │  ├─ session.py
│  │  └─ models.py
│  ├─ schemas/
│  │  ├─ tg_message.py
│  │  ├─ parsed_message.py
│  │  ├─ normalized_title.py
│  │  ├─ resource.py
│  │  └─ wordpress.py
│  ├─ collectors/
│  │  └─ telegram_listener.py
│  ├─ parsers/
│  │  └─ tg_message_parser.py
│  ├─ normalizers/
│  │  ├─ title_normalizer.py
│  │  └─ slug_builder.py
│  ├─ services/
│  │  ├─ category_detector.py
│  │  ├─ dedup_service.py
│  │  ├─ resource_service.py
│  │  ├─ article_service.py
│  │  ├─ wordpress_publisher.py
│  │  └─ go_redirect_service.py
│  ├─ templates/
│  │  └─ post_template.html.j2
│  └─ main.py
├─ scripts/
│  ├─ run_listener.py
│  ├─ reprocess_message.py
│  └─ init_db.py
├─ tests/
│  ├─ test_parser.py
│  ├─ test_normalizer.py
│  ├─ test_dedup.py
│  └─ test_article_service.py
├─ docs/
│  └─ tg2blog_stage1_spec.md
├─ .env.example
├─ requirements.txt
├─ Dockerfile
└─ docker-compose.yml
```

---

## 7. 配置项定义

AI 需要生成 `.env.example`，至少包含以下配置：

```env
APP_ENV=development
APP_DEBUG=true

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=tg2blog
DB_USER=root
DB_PASSWORD=123456

TG_API_ID=
TG_API_HASH=
TG_SESSION_NAME=tg2blog
TG_CHANNELS=movie_channel_a,movie_channel_b

WP_BASE_URL=https://your-wp-site.com
WP_USERNAME=
WP_APP_PASSWORD=

SITE_BASE_URL=https://your-content-site.com
GO_PATH_PREFIX=/go

ZHUIJU_BASE_URL=https://www.zhuiju.us

QQ_GROUP_URL=https://qm.qq.com/xxxx
QQ_CHANNEL_URL=https://pd.qq.com/xxxx

BACKUP_QUARK_URL=https://...
BACKUP_BAIDU_URL=https://...
BACKUP_UC_URL=https://...
BACKUP_XUNLEI_URL=https://...
```

---

## 8. 数据模型定义

AI 需要优先实现以下 SQLAlchemy 模型。

### 8.1 `TgMessage`

字段：

- id
- channel_id
- channel_name
- message_id
- message_date
- raw_text
- raw_image_url
- raw_json
- created_at

唯一索引：

- `(channel_id, message_id)`

---

### 8.2 `Resource`

字段：

- id
- canonical_title
- alias_title
- year
- category
- search_keyword
- description_raw
- summary
- cover_image_url
- status
- created_at
- updated_at

唯一索引：

- `(canonical_title, year, category)`

---

### 8.3 `ResourceLink`

字段：

- id
- resource_id
- drive_type
- share_id
- original_url
- created_at

唯一索引：

- `(drive_type, share_id)`

---

### 8.4 `Article`

字段：

- id
- resource_id
- wp_post_id
- wp_slug
- title_published
- published_at
- status
- created_at

---

### 8.5 `GoClickLog`

字段：

- id
- resource_id
- article_id
- search_keyword
- referer
- user_agent
- ip_hash
- created_at

---

## 9. Pydantic Schema 定义

AI 需要实现以下数据结构。

### 9.1 `ParsedMessage`
字段：

- title_raw: str | None
- description_raw: str | None
- ali_url: str | None
- quark_url: str | None
- baidu_url: str | None
- uc_url: str | None
- xunlei_url: str | None
- size_text: str | None
- tags_raw: list[str]
- cover_image_url: str | None

### 9.2 `NormalizedTitle`
字段：

- canonical_title: str
- alias_title: str | None
- year: int | None
- search_keyword: str

### 9.3 `ResourceCandidate`
字段：

- canonical_title
- alias_title
- year
- category
- search_keyword
- description_raw
- summary
- cover_image_url
- tags

---

## 10. 模块职责定义

### 10.1 `telegram_listener.py`
职责：

- 监听指定 TG 频道
- 只接收新消息
- 将消息转换为内部统一结构
- 调用 `process_message()` 主流程

要求：

- 支持频道白名单
- 支持日志输出
- 不要把业务逻辑写在监听器里

---

### 10.2 `tg_message_parser.py`
职责：

把固定格式 TG 文本解析为 `ParsedMessage`

必须支持提取：

- 名称
- 描述
- 阿里链接
- 夸克链接
- 百度链接
- UC 链接
- 迅雷链接
- 大小
- 标签
- 海报图 URL

要求：

- 使用规则解析
- 支持字段缺失
- 返回结构化对象
- 对异常输入要容错

---

### 10.3 `title_normalizer.py`
职责：

从 `title_raw` 中提取：

- `canonical_title`
- `alias_title`
- `year`
- `search_keyword`

要求：

- 去除噪声词
- 去除年份块后再处理
- 尽量保留中文主标题
- `search_keyword` 必须尽量短

---

### 10.4 `category_detector.py`
职责：

根据标题、描述、标签判断资源分类。

第一阶段规则化即可。

输出：

- 电影
- 剧集
- 动漫
- 综艺
- 软件
- 课程
- 其他

---

### 10.5 `dedup_service.py`
职责：

完成三层去重：

1. 消息级去重
2. 链接级去重
3. 资源级去重

必须对外暴露清晰的方法，例如：

- `is_duplicate_message()`
- `find_resource_by_links()`
- `find_resource_by_resource_key()`

---

### 10.6 `resource_service.py`
职责：

- 组合解析结果 + 标准化结果 + 分类结果
- 生成 `ResourceCandidate`
- 创建新资源
- 保存资源链接

---

### 10.7 `article_service.py`
职责：

- 生成标题
- 生成 slug
- 生成 summary
- 渲染 HTML 正文
- 生成 WordPress 发布 payload

---

### 10.8 `wordpress_publisher.py`
职责：

- 通过 WordPress REST API 发文
- 返回 `wp_post_id`
- 处理失败重试和错误日志

---

### 10.9 `go_redirect_service.py`
职责：

- 生成中间页路径
- 提供跳转目标 URL

注意：  
第一阶段可以只负责“构造 go url”，实际 go 路由可后续接入你现有站点或单独小服务。

---

## 11. 固定格式 TG 解析规则

### 输入示例

```text
名称：大侦探福尔摩斯 Sherlock Holmes (2009)

描述：大侦探福尔摩斯（小罗伯特·唐尼 Robert Downer Jr. 饰）即使在置人于死地之时也异常的逻辑清晰……

阿里：https://www.alipan.com/s/LqNeerS6idB
夸克：https://pan.quark.cn/s/5284716ccbec

📁 大小：NG
🏷 标签：#动作 #悬疑 #犯罪
```

### 提取规则

#### 标题
匹配：

```regex
^名称[：:]\s*(.+)$
```

#### 描述
从 `描述：` 后开始，直到下一个字段块前结束。

停止块头包括：

- 阿里：
- 夸克：
- 百度：
- UC：
- 迅雷：
- 📁 大小：
- 🏷 标签：

#### 链接
分别匹配各网盘字段。

#### 大小
匹配：

```regex
大小[：:]\s*([^\n]+)
```

#### 标签
从标签行提取 `#标签`

---

## 12. 标题标准化规则

### 输入
`大侦探福尔摩斯 Sherlock Holmes (2009)`

### 输出
- canonical_title = `大侦探福尔摩斯`
- alias_title = `Sherlock Holmes`
- year = `2009`
- search_keyword = `大侦探福尔摩斯`

### 处理步骤

1. 提取年份
2. 删除年份片段
3. 删除噪声词
4. 尝试拆中文主标题和英文别名
5. 生成极简 `search_keyword`

### 噪声词列表示例

- 4K
- 1080P
- 2160P
- 高清
- 超清
- 国语
- 中字
- 双语
- 完整版
- 高码版
- 夸克
- 百度
- 阿里
- 网盘
- 全集
- 更新至

---

## 13. 去重规则

### 13.1 消息级去重
唯一键：

```text
channel_id + message_id
```

### 13.2 链接级去重
根据网盘链接提取 `share_id`。

示例：

- `https://www.alipan.com/s/LqNeerS6idB` → `alipan:LqNeerS6idB`
- `https://pan.quark.cn/s/5284716ccbec` → `quark:5284716ccbec`

### 13.3 资源级去重
资源键：

```text
canonical_title + year + category
```

### 13.4 去重优先级
1. 消息级
2. 链接级
3. 资源级

---

## 14. 文章生成规则

### 14.1 标题模板
固定模板随机选择其一：

- `{资源名} 网盘资源整理`
- `{资源名} 下载资源合集`
- `{资源名} 高清资源获取方式`

### 14.2 slug 规则
基于 `canonical_title` 生成拼音或安全 slug。

例如：

- `大侦探福尔摩斯` → `da-zhen-tan-fu-er-mo-si`

### 14.3 summary 规则
第一阶段用规则模板生成。

示例：

```text
这里整理了《大侦探福尔摩斯》的相关资源信息，包括剧情简介、常见网盘来源和获取方式说明。由于资源链接会动态变化，建议前往 zhuiju.us 搜索“大侦探福尔摩斯”实时获取最新可用资源。
```

### 14.4 正文模块
正文必须包含：

1. 资源简介
2. 剧情简介（直接使用 `description_raw`）
3. 资源信息
4. 获取方式

---

## 15. 获取方式模块规则

### 第一层：主入口
跳转到中间页：

```text
/go/{slug}
```

中间页最终跳到：

```text
https://www.zhuiju.us/s/{search_keyword}.html
```

### 第二层：社群入口
固定放：

- QQ 群链接
- QQ 频道链接

### 第三层：备用入口
固定放：

- 夸克导流链接
- 百度导流链接
- UC 导流链接
- 迅雷导流链接

---

## 16. WordPress 发布 payload 要求

AI 需要实现一个函数，生成 REST API payload，至少包括：

```json
{
  "title": "大侦探福尔摩斯 网盘资源整理",
  "status": "publish",
  "slug": "da-zhen-tan-fu-er-mo-si",
  "excerpt": "这里整理了《大侦探福尔摩斯》的相关资源信息……",
  "content": "<h2>资源简介</h2>...",
  "categories": [],
  "tags": []
}
```

---

## 17. 主流程定义

AI 需要实现 `process_message()` 主流程，逻辑顺序固定：

1. 判定是否重复消息
2. 保存原始消息
3. 解析 TG 文本
4. 标题标准化
5. 分类判定
6. 组装资源候选对象
7. 链接级去重
8. 资源级去重
9. 新建资源
10. 保存资源链接
11. 构造文章
12. 发布到 WordPress
13. 保存文章记录
14. 返回处理结果

---

## 18. 错误处理要求

AI 生成代码时必须遵守：

1. 不允许裸 `except`
2. 所有关键步骤要有日志
3. WordPress 发布失败不能导致进程崩溃
4. 解析失败要记录原始消息上下文
5. 去重冲突要能追踪原因
6. 所有外部请求必须设置超时

---

## 19. 日志要求

至少打印以下日志：

- 监听到新消息
- 开始解析
- 解析成功/失败
- 标题标准化结果
- 去重命中原因
- 文章发布成功/失败
- WordPress 返回状态
- process_message 最终结果

---

## 20. 测试要求

AI 生成代码时必须同时生成测试。

### 20.1 `test_parser.py`
测试：

- 标准样例能正确提取所有字段
- 缺失某个网盘链接也能正常返回
- 没有标签时返回空列表
- 描述块能正确截断

### 20.2 `test_normalizer.py`
测试：

- 中英文混排标题
- 只有中文标题
- 带年份标题
- 带噪声词标题
- `search_keyword` 是否极简

### 20.3 `test_dedup.py`
测试：

- 重复消息判断
- 重复链接判断
- 重复资源键判断

### 20.4 `test_article_service.py`
测试：

- 标题模板生成
- slug 生成
- WordPress payload 生成
- 正文中是否包含 3 层获取方式

---

## 21. 开发顺序

AI 必须按以下顺序实现，不要跳步。

### P0-1
- 配置模块
- 数据库模型
- Pydantic schemas

### P0-2
- TG 固定格式消息解析器
- 标题标准化器
- 分类判定器

### P0-3
- 去重服务
- 资源服务

### P0-4
- 文章服务
- WordPress 发布器

### P0-5
- 主流程 `process_message()`
- 监听器接入

### P0-6
- 测试补齐
- Docker 化

---

## 22. 完成标准

第一阶段完成后，应满足：

1. 监听指定 TG 频道新消息
2. 消息被解析成结构化数据
3. 重复消息不会重复处理
4. 同一资源不会反复发布多篇文章
5. WordPress 中能看到发布成功的文章
6. 文章主入口跳转逻辑正确
7. 文章含 QQ 群、QQ 频道、4 个固定网盘导流入口

---

# 给 VSCode 里 AI 的推荐下发方式

下面这些，是你可以直接复制给 Claude / GPT-5.4 的命令模板。

---

## 命令模板 1：初始化项目骨架

```text
请基于 docs/tg2blog_stage1_spec.md，为我初始化一个 Python 3.11 项目骨架。

要求：
1. 严格按照文档中的目录结构创建文件
2. 优先实现配置模块、数据库模型、Pydantic schemas
3. 暂时不要写监听 Telegram 和发布 WordPress 的真实外部调用
4. 所有代码要有类型注解
5. 所有模块都要有清晰的 docstring
6. 输出完整代码，不要只给示例
```

---

## 命令模板 2：实现解析器

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现 TG 固定格式消息解析器 app/parsers/tg_message_parser.py。

要求：
1. 输入为 raw_text 和 cover_image_url
2. 输出为 ParsedMessage schema
3. 必须正确解析 名称、描述、阿里、夸克、百度、UC、迅雷、大小、标签、封面图
4. 对字段缺失要容错
5. 同时为 tests/test_parser.py 编写完整 pytest 测试
6. 输出完整代码
```

---

## 命令模板 3：实现标题标准化

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现标题标准化模块 app/normalizers/title_normalizer.py。

要求：
1. 输入为 title_raw
2. 输出 canonical_title、alias_title、year、search_keyword
3. search_keyword 必须极简，只保留真实资源名
4. 要处理 中英文混排、年份、噪声词
5. 同时编写 tests/test_normalizer.py
6. 输出完整代码
```

---

## 命令模板 4：实现去重服务

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现去重服务 app/services/dedup_service.py。

要求：
1. 实现消息级去重、链接级去重、资源级去重
2. 设计清晰的 service API
3. 使用 SQLAlchemy 模型
4. 同时为 tests/test_dedup.py 编写测试
5. 输出完整代码
```

---

## 命令模板 5：实现文章生成和发布

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现：
1. app/services/article_service.py
2. app/services/wordpress_publisher.py
3. tests/test_article_service.py

要求：
1. 文章必须包含资源简介、剧情简介、资源信息、获取方式
2. 获取方式必须包含三层：主入口、社群入口、备用入口
3. 主入口必须跳转 /go/{slug}
4. WordPress publisher 先实现真实 REST API 调用代码
5. 要有超时、错误处理、日志
6. 输出完整代码
```

---

## 命令模板 6：实现主流程

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现消息处理主流程 process_message()。

要求：
1. 严格按文档定义的顺序处理
2. 将逻辑拆到 service 层，不要写成巨型函数
3. 返回结构化处理结果
4. 为关键流程添加日志
5. 优先保证可测试性
6. 输出完整代码
```

---

## 命令模板 7：最后接 Telegram 监听

```text
请严格基于 docs/tg2blog_stage1_spec.md，实现 Telegram 指定频道监听器。

要求：
1. 使用 Telethon
2. 仅监听配置中的频道白名单
3. 仅处理新消息
4. 收到消息后调用 process_message()
5. 出错不能导致监听器退出
6. 输出完整代码和运行说明
```

---

# 你现在最推荐的执行顺序

你到 VSCode 后，建议就按这个顺序下命令：

先执行 1  
再执行 2  
再执行 3  
再执行 4  
再执行 5  
再执行 6  
最后执行 7

不要一上来就让模型“一次写完整个项目”，那样最容易漂。

---

# 你现在就该保存的两个文件名

建议你先准备这两个文档文件：

```text
docs/tg2blog_stage1_prd.md
docs/tg2blog_stage1_spec.md
```

其中：

- `prd.md` 放我上一条给你的 PRD
- `spec.md` 放我这条给你的开发任务拆解文档

这样你在 VSCode 里，只要一句话：

```text
请严格根据 docs/tg2blog_stage1_prd.md 和 docs/tg2blog_stage1_spec.md 开发，不要偏离文档。
```

模型就比较不容易跑偏。
