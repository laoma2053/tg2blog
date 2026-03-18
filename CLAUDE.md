# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

tg2blog 是一个基于 Telegram 频道监听的资源内容自动发布系统。监听指定 TG 频道消息，解析资源信息（电影、剧集等），经过去重判断后自动发布到 WordPress 内容站，最终导流到 www.zhuiju.us 搜索站。

**技术栈：** Python 3.11+, Telethon, SQLAlchemy, MySQL, WordPress REST API, httpx, pydantic

## 核心业务流程

```
TG频道监听 → 消息解析 → 标题标准化 → 三层去重 → 资源创建 → WordPress发布 → 中间页跳转
```

**三层去重机制：**
1. 消息级去重：`(channel_id, message_id)` 唯一
2. 链接级去重：网盘分享链接指纹（如 `alipan:LqNeerS6idB`）
3. 资源级去重：`(canonical_title, year, category)` 唯一

## 项目结构

```
app/
├── core/           # 配置、日志、常量
├── db/             # 数据库模型和会话
├── schemas/        # Pydantic 数据结构
├── collectors/     # TG 监听器
├── parsers/        # 消息解析器
├── normalizers/    # 标题标准化、slug 生成
├── services/       # 业务逻辑层
│   ├── category_detector.py
│   ├── dedup_service.py
│   ├── resource_service.py
│   ├── article_service.py
│   ├── wordpress_publisher.py
│   └── process_message_service.py
└── templates/      # HTML 模板

scripts/            # 运行脚本
tests/              # 测试文件
docs/               # 项目文档（PRD、Spec、接口定义）
```

## 常用命令

### 环境设置
```bash
# 安装依赖
pip install -r requirements.txt

# 复制配置文件
cp .env.example .env
# 编辑 .env 填入必要配置
```

### 数据库初始化
```bash
python scripts/init_db.py
```

### 运行测试
```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_parser.py

# 运行特定测试用例
pytest tests/test_parser.py::test_parse_standard_message

# 显示详细输出
pytest -v

# 显示测试覆盖率
pytest --cov=app
```

### Telegram 认证
```bash
# 首次使用前必须完成认证（生成 session 文件）
python scripts/auth_telegram.py
# 按提示输入手机号（带国际区号，如 +8613800138000）和验证码
```

### 运行监听器
```bash
python scripts/run_listener.py
```

### Docker 运行
```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 关键设计约束

### 1. search_keyword 必须极简
`search_keyword` 只保留真实资源名，禁止包含：4K、高清、国语、中字、百度、夸克、阿里、网盘、完整版、全集等噪声词。

**正确：** `流浪地球2`
**错误：** `流浪地球2 4K 国语中字 夸克`

### 2. description_raw 必须完整保存
TG 消息中的"描述："字段是文章正文的重要来源，必须完整入库，不能丢失。

### 3. 主流程顺序固定
`process_message()` 的处理顺序严格按照文档定义，不可随意调整：
1. 判断重复消息 → 2. 保存原始消息 → 3. 解析消息 → 4. 标题标准化 → 5. 分类判定 → 6. 构造资源候选对象 → 7. 提取链接指纹 → 8. 链接级去重 → 9. 资源级去重 → 10. 创建资源 → 11. 保存资源链接 → 12. 构造文章 → 13. 发布 WordPress → 14. 保存文章记录 → 15. 返回结果

### 4. 文章获取方式三层结构
每篇文章必须包含：
- **第一层：** 主入口按钮 → `/go/{slug}` → 302 跳转到 `www.zhuiju.us/s/{search_keyword}.html`
- **第二层：** QQ 群入口 + QQ 频道入口
- **第三层：** 4 个固定网盘导流链接（夸克、百度、UC、迅雷）

### 5. 模块分层约束
- **parsers** 只负责解析，不访问数据库
- **normalizers** 只负责标准化，不调外部 API
- **services** 负责业务逻辑编排
- **collectors** 只负责接入，不写复杂业务逻辑

## 开发指导

### 实现新功能的推荐顺序
1. 先实现配置、数据模型、Pydantic schemas
2. 再实现解析器和标准化器（带测试）
3. 然后实现去重和资源服务（带测试）
4. 接着实现文章生成和 WordPress 发布（带测试）
5. 最后实现主流程和 TG 监听器

### 代码规范
- 所有代码必须有类型注解
- 所有公共函数必须有 docstring
- 所有外部调用必须设置 timeout
- 必须为核心模块编写 pytest 测试
- 不允许裸 `except`，必须明确异常类型

### 测试要求
每个核心模块都必须有对应的测试文件：
- `test_parser.py` - 测试标准样例、缺失字段、边界情况
- `test_normalizer.py` - 测试中英文混排、噪声词清理、年份提取
- `test_dedup.py` - 测试三层去重逻辑
- `test_article_service.py` - 测试文章生成、三层获取方式
- `test_process_message_service.py` - 测试主流程各种分支

## 重要文档

项目有三份核心文档，修改代码前必须参考：
- `docs/tg2blog_stage1_prd.md` - 产品需求文档
- `docs/tg2blog_stage1_spec.md` - 技术规格和开发任务拆解
- `docs/tg2blog_stage1_interfaces_and_tests.md` - 接口定义和测试用例清单

**修改代码时严格遵循这三份文档的定义，不要擅自改变字段名、接口签名或业务逻辑顺序。**

## 第一阶段边界

**本阶段实现：** TG 监听、固定格式解析、标题标准化、三层去重、WordPress 自动发布、中间页跳转

**本阶段不实现：** 热度评分、Tavily、DeepSeek、全网采集、历史回填、后台管理界面、内容增强、多模版分流

## 配置说明

关键环境变量（见 `.env.example`）：
- `TG_API_ID`, `TG_API_HASH` - Telegram API 凭证
- `TG_CHANNELS` - 监听的频道白名单（逗号分隔）
- `WP_BASE_URL`, `WP_USERNAME`, `WP_APP_PASSWORD` - WordPress 发布凭证
- `ZHUIJU_BASE_URL` - 搜索站地址（默认 https://www.zhuiju.us）
- `QQ_GROUP_URL`, `QQ_CHANNEL_URL` - 社群入口
- `BACKUP_*_URL` - 4 个固定网盘导流链接

## 故障排查

### TG 监听器无法启动
- 检查 `TG_API_ID` 和 `TG_API_HASH` 是否正确
- 检查 `TG_CHANNELS` 配置的频道是否存在
- 查看 Telethon session 文件是否需要重新认证

### WordPress 发布失败
- 检查 `WP_APP_PASSWORD` 是否有效（不是普通密码）
- 检查 WordPress REST API 是否启用
- 查看 WordPress 日志确认权限问题

### 去重不生效
- 检查数据库唯一索引是否正确创建
- 查看日志确认去重命中原因
- 验证 `canonical_title`、`year`、`category` 标准化结果是否一致
