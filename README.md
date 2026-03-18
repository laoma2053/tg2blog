# tg2blog

基于 Telegram 频道监听的资源内容自动发布系统

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入必要配置
```

### 3. 初始化数据库

```bash
python scripts/init_db.py
```

### 4. 运行测试

```bash
pytest
```

## 项目结构

```
app/
├── core/           # 配置、日志、常量
├── db/             # 数据库模型
├── schemas/        # Pydantic 数据结构
├── parsers/        # TG 消息解析器
├── normalizers/    # 标题标准化、slug 生成
└── services/       # 业务逻辑层
```

## 核心流程

```
TG监听 → 消息解析 → 标题标准化 → 三层去重 → 资源创建 → WordPress发布
```

## 文档

详细文档请参考：
- `docs/tg2blog_stage1_prd.md` - 产品需求文档
- `docs/tg2blog_stage1_spec.md` - 技术规格
- `docs/tg2blog_stage1_interfaces_and_tests.md` - 接口定义
- `CLAUDE.md` - 开发指南
