# tg2blog 项目 PRD（第一阶段）

## 1. 项目名称

**tg2blog：基于指定 Telegram 频道监听的资源内容自动发布系统**

---

## 2. 项目背景

当前已存在两个独立系统：

### 2.1 搜索交付站
域名：`www.zhuiju.us`

作用：

- 用户搜索资源
- 调用 PanSou API
- 获取来自 TG 频道、QQ 频道、微博、插件等来源的网盘资源线索
- 执行转存
- 重新分享给用户

`www.zhuiju.us` 是 **搜索站 / 交付站**，不是内容沉淀站。

---

### 2.2 内容站（待建设）
采用 WordPress 搭建独立资源站，用于：

- 发布资源介绍类文章
- 获取 SEO 流量
- 获取 AI 抓取流量
- 给 `www.zhuiju.us` 导流
- 提供 QQ 群 / QQ 频道 / 备用网盘导流入口

内容站与搜索站保持独立。

---

## 3. 项目目标

第一阶段目标不是做全自动采集平台，而是做一条 **高质量、稳定、可持续的自动内容生产线**。

### 3.1 第一阶段必须完成的目标

1. 监听用户指定的 TG 频道消息更新
2. 解析 TG 消息为结构化数据
3. 标准化资源标题，提取真实搜索关键词
4. 对资源进行去重判断
5. 非重复资源自动发布到 WordPress
6. 文章主入口通过中间页跳转到 `www.zhuiju.us` 对应搜索页
7. 每篇文章固定插入：
   - 主获取入口
   - QQ 群入口
   - QQ 频道入口
   - 4 个固定网盘导流链接

---

### 3.2 第一阶段暂不做

1. 全网采集
2. 大规模历史回填
3. 热度评分系统
4. Tavily + DeepSeek 内容增强
5. 搜索次数分析
6. 自动分流实验
7. 多语言/多模版内容增强

---

## 4. 核心业务流程

```text
指定TG频道
   ↓
监听新消息
   ↓
消息解析
   ↓
标题标准化
   ↓
去重判断
   ↓
生成文章数据
   ↓
发布到 WordPress
   ↓
文章内主按钮跳转中间页
   ↓
中间页 302 到 www.zhuiju.us/s/真实资源名.html
```

---

## 5. 输入数据来源

### 5.1 数据来源定义
系统只监听用户手工指定的高质量 TG 频道。

不做全网搜索采集，不主动扫公开平台。

### 5.2 监听方式
监听指定频道的新消息更新，当有新消息到达时立即进入处理流程。

### 5.3 频道配置方式
通过配置文件或数据库维护频道白名单，例如：

```yaml
telegram:
  channels:
    - movie_channel_a
    - movie_channel_b
    - tv_channel_c
```

---

## 6. TG 消息格式假设

第一阶段先基于较规整的固定格式处理。

### 6.1 样例格式

```text
名称：大侦探福尔摩斯 Sherlock Holmes (2009)

描述：大侦探福尔摩斯（小罗伯特·唐尼 Robert Downer Jr. 饰）即使在置人于死地之时也异常的逻辑清晰，然而办案时有条不紊的他在私底下的生活中简直就是个“怪胎”，至少在他的助手华生医生（裘德·洛 Jude Law饰）眼中他是这样一个人。他们亲手绳之以法的“黑暗巫师”布莱克大人（马克·斯特朗 Mark Strong 饰）在临死前说死亡即是开始，随后艾琳·艾德勒（瑞秋·麦克亚当斯 Rachel McAdams 饰）出现在他的身边要他帮忙找个失踪的人，而她身边有个影子般可怕人物。

阿里：https://www.alipan.com/s/LqNeerS6idB
夸克：https://pan.quark.cn/s/5284716ccbec

📁 大小：NG
🏷 标签：#动作 #悬疑 #犯罪
```

消息最前面通常带一张海报图片。

---

## 7. 结构化字段定义

### 7.1 原始消息字段

```json
{
  "channel_id": "",
  "channel_name": "",
  "message_id": "",
  "message_date": "",
  "raw_text": "",
  "raw_image_url": "",
  "raw_json": {}
}
```

### 7.2 解析后字段

```json
{
  "title_raw": "大侦探福尔摩斯 Sherlock Holmes (2009)",
  "description_raw": "大侦探福尔摩斯（小罗伯特·唐尼 ...）",
  "ali_url": "https://www.alipan.com/s/LqNeerS6idB",
  "quark_url": "https://pan.quark.cn/s/5284716ccbec",
  "size_text": "NG",
  "tags_raw": ["动作", "悬疑", "犯罪"],
  "cover_image_url": "https://..."
}
```

### 7.3 标准资源字段

```json
{
  "canonical_title": "大侦探福尔摩斯",
  "alias_title": "Sherlock Holmes",
  "year": 2009,
  "category": "电影",
  "search_keyword": "大侦探福尔摩斯",
  "description_raw": "大侦探福尔摩斯（小罗伯特·唐尼 ...）",
  "summary": "这里整理了《大侦探福尔摩斯》的相关资源信息...",
  "tags": ["动作", "悬疑", "犯罪"],
  "cover_image_url": "https://..."
}
```

---

## 8. 字段说明

### 8.1 `title_raw`
TG 消息中“名称：”后面的完整原始标题。

### 8.2 `description_raw`
TG 消息中“描述：”后面的完整正文描述。  
这是文章正文的重要来源，必须入库，不能丢。

### 8.3 `canonical_title`
资源标准中文名，用于：

- 文章标题生成
- 资源去重
- 资源归并

### 8.4 `alias_title`
英文名或别名，用于：

- 补充文章信息
- 去重辅助
- 后续增强

### 8.5 `year`
年份，例如 `2009`。

### 8.6 `category`
资源类型，第一阶段先支持：

- 电影
- 剧集
- 动漫
- 综艺
- 软件
- 课程
- 其他

### 8.7 `search_keyword`
给 `www.zhuiju.us` 搜索使用的关键词。  
必须尽可能短，只保留真实资源名。

例如：

- `大侦探福尔摩斯`
- `流浪地球2`
- `三体`

不能带：

- 4K
- 国语中字
- 夸克
- 百度
- 高清
- 完整版

---

## 9. 去重定义

### 9.1 目标
避免同一个资源重复生成多篇文章。

### 9.2 去重层级

#### 第一层：消息级去重
同一 TG 频道中的同一消息，只处理一次。

唯一键：

```text
channel_id + message_id
```

#### 第二层：链接级去重
如果解析出的网盘分享链接已经存在，则视为已有资源来源，归并到已有资源。

链接指纹示例：

- 阿里：`alipan:LqNeerS6idB`
- 夸克：`quark:5284716ccbec`

#### 第三层：资源级去重
如果标准资源键一致，则视为同一资源。

标准资源键：

```text
canonical_title + year + category
```

#### 第四层：弱模糊匹配（可选兜底）
如果标题高度近似，且年份、分类一致，可判为重复。  
第一阶段可以先保守实现。

---

## 10. 去重判定规则

### 10.1 判定优先级

1. 先判消息唯一键
2. 再判链接指纹
3. 再判标准资源键
4. 最后才新建资源

### 10.2 新资源条件
只有在以下条件都不满足时，才创建新资源并新发文章：

- 不是重复消息
- 未命中已有链接指纹
- 未命中已有标准资源键

---

## 11. 文章发布策略

### 11.1 文章定位
文章是 **资源信息页 / 导流页**，不是直接下载页。

### 11.2 文章标题规则
第一阶段标题采用固定模板，围绕“真实资源名 + 资源词”。

可选模板：

- `{资源名} 网盘资源整理`
- `{资源名} 下载资源合集`
- `{资源名} 高清资源获取方式`

示例：

- `大侦探福尔摩斯 网盘资源整理`
- `流浪地球2 下载资源合集`

### 11.3 文章正文组成

1. 资源简介
2. 基础信息区块
3. 获取方式模块
4. 相关推荐模块（后续可做）

---

## 12. 获取方式模块设计

### 第一层：主入口
按钮跳中间页，再跳到：

```text
https://www.zhuiju.us/s/{search_keyword}.html
```

例如：

```text
https://www.zhuiju.us/s/大侦探福尔摩斯.html
```

### 第二层：社群入口
放：

- QQ 群入口
- QQ 频道入口

### 第三层：备用入口
固定插入 4 个网盘导流链接：

- 夸克
- 百度
- UC
- 迅雷

这些链接内放导流图片/说明，引导去：

- `www.zhuiju.us`
- QQ 群
- QQ 频道

---

## 13. 中间页设计

### 13.1 作用
中间页只做两件事：

1. 记录点击日志
2. 302 跳转到 `www.zhuiju.us`

### 13.2 跳转示例

文章链接：

```text
/go/da-zhen-tan-fu-er-mo-si
```

中间页查询到 `search_keyword = 大侦探福尔摩斯`

302 跳转到：

```text
https://www.zhuiju.us/s/大侦探福尔摩斯.html
```

### 13.3 点击日志字段

- resource_id
- article_id
- search_keyword
- referer
- user_agent
- ip_hash
- created_at

---

## 14. 数据库设计（第一阶段）

### 14.1 `tg_messages`

```sql
CREATE TABLE tg_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  channel_id VARCHAR(128) NOT NULL,
  channel_name VARCHAR(255),
  message_id VARCHAR(128) NOT NULL,
  message_date DATETIME,
  raw_text LONGTEXT,
  raw_image_url TEXT,
  raw_json JSON,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_channel_message (channel_id, message_id)
);
```

### 14.2 `resources`

```sql
CREATE TABLE resources (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  canonical_title VARCHAR(255) NOT NULL,
  alias_title VARCHAR(255),
  year INT,
  category VARCHAR(64),
  search_keyword VARCHAR(255) NOT NULL,
  description_raw LONGTEXT,
  summary LONGTEXT,
  cover_image_url TEXT,
  status VARCHAR(32) DEFAULT 'active',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_resource (canonical_title, year, category)
);
```

### 14.3 `resource_links`

```sql
CREATE TABLE resource_links (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  resource_id BIGINT NOT NULL,
  drive_type VARCHAR(32) NOT NULL,
  share_id VARCHAR(255) NOT NULL,
  original_url TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_drive_share (drive_type, share_id)
);
```

### 14.4 `articles`

```sql
CREATE TABLE articles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  resource_id BIGINT NOT NULL,
  wp_post_id BIGINT,
  wp_slug VARCHAR(255),
  title_published VARCHAR(255),
  published_at DATETIME,
  status VARCHAR(32) DEFAULT 'published',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 14.5 `go_click_logs`

```sql
CREATE TABLE go_click_logs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  resource_id BIGINT,
  article_id BIGINT,
  search_keyword VARCHAR(255),
  referer TEXT,
  user_agent TEXT,
  ip_hash VARCHAR(128),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 15. TG 固定格式消息解析器规格

### 15.1 目标
把 TG 消息文本解析为结构化字段。

### 15.2 输入
原始 TG 文本 + 海报图片 URL。

### 15.3 输出

```json
{
  "title_raw": "",
  "description_raw": "",
  "ali_url": "",
  "quark_url": "",
  "baidu_url": "",
  "uc_url": "",
  "xunlei_url": "",
  "size_text": "",
  "tags_raw": [],
  "cover_image_url": ""
}
```

### 15.4 解析规则

#### 标题解析
匹配：

```regex
^名称[：:]\s*(.+)$
```

多行模式下取第一处匹配。

#### 描述解析
匹配从 `描述：` 开始，到下一个已知字段块前结束。

建议逻辑：

- 找到 `描述[：:]`
- 从该位置开始截取
- 遇到以下块头之一停止：
  - `阿里：`
  - `夸克：`
  - `百度：`
  - `UC：`
  - `迅雷：`
  - `📁 大小：`
  - `🏷 标签：`

#### 链接解析
分别匹配：

```regex
阿里[：:]\s*(https?://[^\s]+)
夸克[：:]\s*(https?://[^\s]+)
百度[：:]\s*(https?://[^\s]+)
UC[：:]\s*(https?://[^\s]+)
迅雷[：:]\s*(https?://[^\s]+)
```

#### 大小解析

```regex
大小[：:]\s*([^\n]+)
```

#### 标签解析
匹配 `标签：` 后面的内容，再提取 `#标签`。

例如：

```regex
#([^\s#]+)
```

---

## 16. 标题标准化规则

### 16.1 输入
`title_raw`

例如：

```text
大侦探福尔摩斯 Sherlock Holmes (2009)
```

### 16.2 输出

```json
{
  "canonical_title": "大侦探福尔摩斯",
  "alias_title": "Sherlock Holmes",
  "year": 2009,
  "search_keyword": "大侦探福尔摩斯"
}
```

### 16.3 规则步骤

#### 步骤 1：提取年份
匹配 4 位年份：

```regex
\((19|20)\d{2}\)
```

或：

```regex
(19|20)\d{2}
```

如果存在，提取为 `year`。

#### 步骤 2：删除年份块
从原始标题中去掉 `(2009)` 这类年份片段。

#### 步骤 3：识别中英文混排
若标题前半部分为中文，后半部分为英文，优先：

- 中文部分作为 `canonical_title`
- 英文部分作为 `alias_title`

例如：

```text
大侦探福尔摩斯 Sherlock Holmes
```

输出：

- `canonical_title = 大侦探福尔摩斯`
- `alias_title = Sherlock Holmes`

#### 步骤 4：移除附加资源词
删除：

- 4K
- 1080P
- 高清
- 国语
- 中字
- 双语
- 完整版
- 夸克
- 百度
- 阿里
- 网盘
- 全集
- 更新至xx集

#### 步骤 5：生成 `search_keyword`
`search_keyword` 默认取 `canonical_title`。  
必须尽量短，不拼附加描述词。

---

## 17. 分类判定规则

第一阶段先用简单规则。

### 17.1 根据标签和标题判断

如果标签中包含：

- 动作
- 悬疑
- 犯罪
- 爱情
- 科幻

优先判为：`电影`

如果出现：

- 全xx集
- 更新至xx集
- 第xx集

优先判为：`剧集`

如果标题中出现：

- v1.0
- Win/Mac
- 安装包
- 破解

优先判为：`软件`

第一阶段允许误差，后面再优化。

---

## 18. 去重判定伪代码

```python
def process_message(message):
    # 1. 消息级去重
    if exists_tg_message(message.channel_id, message.message_id):
        return {"status": "skip", "reason": "duplicate_message"}

    save_raw_tg_message(message)

    # 2. 解析消息
    parsed = parse_tg_message(message.raw_text, message.cover_image_url)

    # 3. 标题标准化
    normalized = normalize_title(parsed["title_raw"])

    # 4. 分类判定
    category = detect_category(
        title_raw=parsed["title_raw"],
        description_raw=parsed["description_raw"],
        tags_raw=parsed["tags_raw"]
    )

    # 5. 生成标准资源对象
    resource_candidate = {
        "canonical_title": normalized["canonical_title"],
        "alias_title": normalized["alias_title"],
        "year": normalized["year"],
        "category": category,
        "search_keyword": normalized["canonical_title"],
        "description_raw": parsed["description_raw"],
        "summary": build_summary(
            canonical_title=normalized["canonical_title"],
            description_raw=parsed["description_raw"]
        ),
        "cover_image_url": parsed["cover_image_url"]
    }

    # 6. 链接级去重
    share_fingerprints = extract_share_fingerprints(parsed)
    existing_resource = find_resource_by_share_fingerprints(share_fingerprints)
    if existing_resource:
        save_resource_links(existing_resource.id, parsed)
        return {"status": "merged", "reason": "duplicate_by_link", "resource_id": existing_resource.id}

    # 7. 资源级去重
    existing_resource = find_resource_by_key(
        canonical_title=resource_candidate["canonical_title"],
        year=resource_candidate["year"],
        category=resource_candidate["category"]
    )
    if existing_resource:
        save_resource_links(existing_resource.id, parsed)
        return {"status": "merged", "reason": "duplicate_by_resource_key", "resource_id": existing_resource.id}

    # 8. 新建资源
    resource_id = create_resource(resource_candidate)
    save_resource_links(resource_id, parsed)

    # 9. 生成文章数据
    post_data = build_wp_post_data(resource_id, resource_candidate, parsed)

    # 10. 发布文章
    wp_result = publish_to_wordpress(post_data)

    # 11. 记录文章
    save_article(resource_id, wp_result)

    return {"status": "published", "resource_id": resource_id, "wp_post_id": wp_result["id"]}
```

---

## 19. 消息解析器伪代码

```python
import re

def parse_tg_message(raw_text: str, cover_image_url: str = None) -> dict:
    result = {
        "title_raw": None,
        "description_raw": None,
        "ali_url": None,
        "quark_url": None,
        "baidu_url": None,
        "uc_url": None,
        "xunlei_url": None,
        "size_text": None,
        "tags_raw": [],
        "cover_image_url": cover_image_url
    }

    # 标题
    m = re.search(r'^名称[：:]\s*(.+)$', raw_text, re.MULTILINE)
    if m:
        result["title_raw"] = m.group(1).strip()

    # 描述块
    desc_match = re.search(
        r'描述[：:]\s*(.*?)(?=\n(?:阿里|夸克|百度|UC|迅雷|📁\s*大小|🏷\s*标签)[：:]|\Z)',
        raw_text,
        re.S
    )
    if desc_match:
        result["description_raw"] = desc_match.group(1).strip()

    # 网盘链接
    patterns = {
        "ali_url": r'阿里[：:]\s*(https?://[^\s]+)',
        "quark_url": r'夸克[：:]\s*(https?://[^\s]+)',
        "baidu_url": r'百度[：:]\s*(https?://[^\s]+)',
        "uc_url": r'UC[：:]\s*(https?://[^\s]+)',
        "xunlei_url": r'迅雷[：:]\s*(https?://[^\s]+)',
    }

    for key, pattern in patterns.items():
        m = re.search(pattern, raw_text, re.I)
        if m:
            result[key] = m.group(1).strip()

    # 大小
    m = re.search(r'大小[：:]\s*([^\n]+)', raw_text)
    if m:
        result["size_text"] = m.group(1).strip()

    # 标签
    tag_line = re.search(r'标签[：:]\s*([^\n]+)', raw_text)
    if tag_line:
        result["tags_raw"] = re.findall(r'#([^\s#]+)', tag_line.group(1))

    return result
```

---

## 20. 标题标准化伪代码

```python
import re

NOISE_WORDS = [
    "4K", "1080P", "2160P", "高清", "超清", "国语", "中字", "双语",
    "完整版", "高码版", "夸克", "百度", "阿里", "网盘", "全集"
]

def normalize_title(title_raw: str) -> dict:
    title = title_raw.strip()

    year = None
    m = re.search(r'\((19|20)\d{2}\)', title)
    if m:
        year = int(re.sub(r'[^\d]', '', m.group(0)))
        title = title.replace(m.group(0), '').strip()
    else:
        m = re.search(r'(19|20)\d{2}', title)
        if m:
            year = int(m.group(0))
            title = title.replace(m.group(0), '').strip()

    # 去噪词
    for word in NOISE_WORDS:
        title = re.sub(re.escape(word), '', title, flags=re.I).strip()

    title = re.sub(r'\s+', ' ', title).strip()

    # 尝试中文 + 英文拆分
    chinese_part = None
    english_part = None

    m = re.match(r'^([\u4e00-\u9fff·《》\-—\s]+)\s+([A-Za-z0-9\s\-:\'\"\.]+)$', title)
    if m:
        chinese_part = m.group(1).strip(" 《》")
        english_part = m.group(2).strip()
    else:
        chinese_only = re.findall(r'[\u4e00-\u9fff·]+', title)
        if chinese_only:
            chinese_part = ''.join(chinese_only).strip()

    canonical_title = chinese_part if chinese_part else title.strip(" 《》")
    alias_title = english_part

    search_keyword = canonical_title

    return {
        "canonical_title": canonical_title,
        "alias_title": alias_title,
        "year": year,
        "search_keyword": search_keyword
    }
```

---

## 21. 链接指纹提取伪代码

```python
import re
from urllib.parse import urlparse

def extract_share_fingerprints(parsed: dict) -> list:
    fingerprints = []

    url_map = {
        "alipan": parsed.get("ali_url"),
        "quark": parsed.get("quark_url"),
        "baidu": parsed.get("baidu_url"),
        "uc": parsed.get("uc_url"),
        "xunlei": parsed.get("xunlei_url"),
    }

    for drive_type, url in url_map.items():
        if not url:
            continue

        share_id = extract_share_id(drive_type, url)
        if share_id:
            fingerprints.append({
                "drive_type": drive_type,
                "share_id": share_id,
                "original_url": url
            })

    return fingerprints


def extract_share_id(drive_type: str, url: str) -> str | None:
    if drive_type == "alipan":
        m = re.search(r'/s/([A-Za-z0-9]+)', url)
        return m.group(1) if m else None

    if drive_type == "quark":
        m = re.search(r'/s/([A-Za-z0-9]+)', url)
        return m.group(1) if m else None

    if drive_type == "baidu":
        m = re.search(r'/s/1([A-Za-z0-9_-]+)', url)
        return m.group(1) if m else None

    if drive_type == "uc":
        m = re.search(r'/s/([A-Za-z0-9]+)', url)
        return m.group(1) if m else None

    if drive_type == "xunlei":
        parsed_url = urlparse(url)
        return parsed_url.path.strip('/') or None

    return None
```

---

## 22. WordPress 发布数据规格

### 22.1 输入
构造 `post_data`

### 22.2 输出字段

- `title`
- `slug`
- `status`
- `excerpt`
- `content`
- `categories`
- `tags`
- `featured_media`（可选）

### 22.3 正文模板（第一阶段）

```html
<h2>资源简介</h2>
<p>{summary}</p>

<h2>剧情简介</h2>
<p>{description_raw}</p>

<h2>资源信息</h2>
<ul>
  <li>名称：{canonical_title}</li>
  <li>年份：{year}</li>
  <li>类型：{category}</li>
  <li>大小：{size_text}</li>
  <li>标签：{tags}</li>
</ul>

<h2>获取方式</h2>
<p><a href="/go/{slug}">立即获取《{canonical_title}》资源</a></p>

<h3>社群入口</h3>
<ul>
  <li><a href="{qq_group_url}">加入QQ群获取</a></li>
  <li><a href="{qq_channel_url}">进入QQ频道获取</a></li>
</ul>

<h3>备用获取入口</h3>
<ul>
  <li><a href="{quark_backup_url}">夸克网盘备用入口</a></li>
  <li><a href="{baidu_backup_url}">百度网盘备用入口</a></li>
  <li><a href="{uc_backup_url}">UC网盘备用入口</a></li>
  <li><a href="{xunlei_backup_url}">迅雷网盘备用入口</a></li>
</ul>
```

---

## 23. 第一阶段验收标准

### 功能验收

1. 指定 TG 频道有新消息时，系统能监听到
2. 能从消息中提取：
   - 名称
   - 描述
   - 网盘链接
   - 大小
   - 标签
   - 海报图
3. 能正确生成：
   - `canonical_title`
   - `year`
   - `search_keyword`
4. 能正确判重
5. 非重复资源能自动发布到 WordPress
6. 文章中主入口跳转到正确的 `www.zhuiju.us/s/资源名.html`
7. 文章固定带 QQ 群、QQ 频道、4 个网盘导流链接

### 数据验收

1. 同一 TG 消息不会重复处理
2. 同一资源不会重复生成多篇文章
3. `description_raw` 必须入库
4. `search_keyword` 必须为真实资源名，不带附加噪声词

---

## 24. 实施优先级

### P0
- TG 频道监听
- 固定格式消息解析器
- 标题标准化
- 去重判定
- WordPress 自动发布
- 中间页跳转

### P1
- 热度判断
- Tavily + DeepSeek
- 模板多样化
- 历史回填

---

## 25. 给后续 AI 编码的指令建议

你把这份文档给 Claude / GPT-5.4 后，可以直接这样下任务：

### 任务 1
“请根据这份 PRD，先实现 Python 版 TG 固定格式消息解析器，要求包含单元测试。”

### 任务 2
“请根据这份 PRD，实现标题标准化模块，输入为 `title_raw`，输出为 `canonical_title / alias_title / year / search_keyword`。”

### 任务 3
“请根据这份 PRD，实现 MySQL 表结构 SQL 和 SQLAlchemy 模型。”

### 任务 4
“请根据这份 PRD，实现消息处理主流程 `process_message()`，先不要接真实 TG 和 WP，只写可测试的 service 层。”

### 任务 5
“请根据这份 PRD，实现 WordPress 发布器，要求支持 REST API 发文。”
