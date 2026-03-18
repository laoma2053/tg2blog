# 云服务器部署指南

## 📋 前置要求

- 云服务器（推荐 2核4G 以上）
- Docker 和 Docker Compose
- WordPress 站点（5.6+ 版本）
- 域名（可选，用于 WordPress）

## 🔧 WordPress 配置（重要）

### 1. WordPress 版本要求

- **最低版本**：WordPress 5.6+（内置应用密码功能）
- **推荐版本**：WordPress 6.0+

### 2. 启用 REST API

WordPress 默认已启用 REST API，但需要确认：

**检查 REST API 是否可用：**
```bash
curl https://your-wp-site.com/wp-json/wp/v2/posts
```

如果返回 JSON 数据，说明 REST API 正常。

**常见问题：**
- 如果返回 404，检查伪静态规则是否正确
- 如果返回 403，检查安全插件是否禁用了 REST API

### 3. 生成应用密码

**步骤：**

1. 登录 WordPress 后台：`https://your-wp-site.com/wp-admin`
2. 进入：用户 → 个人资料
3. 滚动到页面底部，找到"应用密码"部分
4. 输入应用名称（如 `tg2blog`）
5. 点击"添加新应用密码"
6. **复制生成的密码**（格式：`xxxx xxxx xxxx xxxx xxxx xxxx`）
7. 将密码填入 `.env` 的 `WP_APP_PASSWORD`（保留空格或去掉都可以）

**注意：**
- 应用密码只显示一次，请妥善保存
- 不是 WordPress 登录密码，是专门的 API 密码
- 可以随时撤销和重新生成

### 4. 用户权限要求

使用的 WordPress 用户必须有**发布文章**权限：
- ✅ 管理员（Administrator）
- ✅ 编辑（Editor）
- ❌ 作者（Author）- 权限不足
- ❌ 订阅者（Subscriber）- 权限不足

### 5. 插件要求

**无需安装任何插件！** WordPress 5.6+ 已内置所需功能。

**可选插件（如遇到问题）：**
- 如果 WordPress < 5.6，安装 `Application Passwords` 插件
- 如果使用了安全插件（如 Wordfence），确保没有禁用 REST API

### 6. 配置示例

```env
# WordPress 配置
WP_BASE_URL=https://blog.example.com  # 站点根地址，不是登录页
WP_USERNAME=admin                      # 有发布权限的用户名
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx   # 应用密码（从后台生成）
```

### 7. 测试连接

配置完成后，可以手动测试 WordPress API：

```bash
# 替换为你的实际配置
curl -X POST https://blog.example.com/wp-json/wp/v2/posts \
  -u "admin:xxxx xxxx xxxx xxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试文章",
    "content": "这是测试内容",
    "status": "draft"
  }'
```

如果返回文章 JSON 数据，说明配置成功！

### 8. 常见 WordPress 问题

**问题 1：401 Unauthorized**
- 检查用户名是否正确
- 检查应用密码是否正确
- 确认用户有发布权限

**问题 2：403 Forbidden**
- 检查安全插件设置（Wordfence、iThemes Security 等）
- 确认 REST API 未被禁用
- 检查服务器防火墙规则

**问题 3：404 Not Found**
- 检查 WordPress 伪静态规则
- 确认 `.htaccess` 文件正确
- Nginx 需要配置 `try_files`

**问题 4：文章发布成功但看不到**
- 检查文章状态是否为 `publish`
- 确认没有被其他插件拦截
- 查看 WordPress 后台的文章列表



## 🚀 快速部署

### 1. 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker
sudo systemctl start docker

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. 克隆项目

```bash
git clone <your-repo-url> tg2blog
cd tg2blog
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env
```

**必填配置项：**
- `TG_API_ID` - Telegram API ID
- `TG_API_HASH` - Telegram API Hash
- `TG_CHANNELS` - 监听的频道列表
- `WP_BASE_URL` - WordPress 站点地址
- `WP_USERNAME` - WordPress 用户名
- `WP_APP_PASSWORD` - WordPress 应用密码
- `DB_PASSWORD` - 数据库密码（建议修改）

### 4. Telegram 认证（重要！必须先完成）

**⚠️ 在启动 Docker 容器前，必须先完成 Telegram 认证，否则容器会不断重启！**

#### 4.1 获取 Telegram API 凭证

1. 访问 https://my.telegram.org
2. 使用手机号登录
3. 进入 "API development tools"
4. 创建应用，获取 `api_id` 和 `api_hash`
5. 填入 `.env` 文件的 `TG_API_ID` 和 `TG_API_HASH`

#### 4.2 本地认证生成 Session 文件

**方法一：在服务器上直接认证（推荐）**

```bash
# 1. 安装 Python 依赖（仅首次需要）
pip3 install telethon python-dotenv pydantic pydantic-settings

# 2. 运行认证脚本
python3 scripts/auth_telegram.py

# 3. 按提示输入信息：
#    - 手机号：必须带国际区号，如 +8613800138000（中国）或 +16602810057（美国）
#    - 验证码：Telegram 会发送到你的手机
#    - 如果启用了两步验证，还需要输入密码

# 4. 认证成功后会生成 tg2blog.session 文件
ls -la *.session
```

**方法二：使用 Bot Token（无需手机验证）**

如果你有 Telegram Bot：

```bash
# 运行认证脚本
python3 scripts/auth_telegram.py

# 输入 Bot Token 而不是手机号
# 格式：123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

#### 4.3 常见认证问题

**问题 1：收不到验证码**
- ✅ 确认手机号格式正确（必须带 `+` 和国家代码）
- ✅ 中国号码：`+86` 开头，如 `+8613800138000`
- ✅ 美国号码：`+1` 开头，如 `+16602810057`
- ✅ 检查 Telegram 是否正常（在手机上打开确认）

**问题 2：API ID/Hash 错误**
```bash
# 检查配置
cat .env | grep TG_API
```
确认从 https://my.telegram.org 获取的凭证正确。

**问题 3：网络连接问题**
```bash
# 测试连接 Telegram 服务器
ping -c 3 149.154.167.50
```

**问题 4：Session 文件权限**
```bash
# 确保 session 文件可读
chmod 644 *.session
```

### 5. 初始化数据库

```bash
# 启动数据库容器
docker-compose up -d db

# 等待数据库就绪（约 10 秒）
sleep 10

# 初始化数据库表结构
docker-compose run --rm app python scripts/init_db.py
```

### 6. 启动完整服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看启动日志
docker-compose logs -f app

# 确认服务正常运行
docker-compose ps
```

**预期日志输出：**
```
tg2blog_app  | 🚀 启动 tg2blog 监听器...
tg2blog_app  | ✅ 已连接到 Telegram
tg2blog_app  | 📡 开始监听频道: @channel1, @channel2
```

**如果看到以下错误，说明 Session 文件有问题：**
```
EOFError: EOF when reading a line
Please enter your phone (or bot token):
```
解决方法：停止容器，重新执行步骤 4 完成认证。

## 📊 服务管理

```bash
# 查看服务状态
docker-compose ps

# 停止服务
docker-compose stop

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f

# 进入容器
docker-compose exec app bash
```

## 🔧 维护操作

### 备份数据库

```bash
docker-compose exec db mysqldump -u root -p${DB_PASSWORD} tg2blog > backup.sql
```

### 恢复数据库

```bash
docker-compose exec -T db mysql -u root -p${DB_PASSWORD} tg2blog < backup.sql
```

### 更新代码

```bash
git pull
docker-compose build
docker-compose up -d
```

## 🛡️ 安全建议

1. **修改默认密码**：务必修改 `.env` 中的 `DB_PASSWORD`
2. **防火墙配置**：只开放必要端口（如 80, 443）
3. **定期备份**：设置定时任务备份数据库
4. **日志监控**：定期检查日志文件

## 📈 性能优化

### 日志轮转

日志已配置自动轮转（最大 10MB，保留 3 个文件）

### 资源限制

如需限制容器资源，修改 `docker-compose.yml`：

```yaml
app:
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 1G
```

## ❓ 常见问题

### 1. 容器启动问题

**问题：app 容器不断重启**
```bash
# 查看详细日志
docker-compose logs app

# 常见原因：
# 1. 未完成 Telegram 认证 → 执行步骤 4
# 2. 数据库未就绪 → 等待 db 容器健康检查通过
# 3. 环境变量配置错误 → 检查 .env 文件
```

**问题：ModuleNotFoundError: No module named 'app'**
```bash
# 检查 Dockerfile 是否包含 PYTHONPATH
grep PYTHONPATH Dockerfile

# 应该看到：ENV PYTHONPATH=/app
# 如果没有，重新构建镜像
docker-compose build --no-cache
```

**问题：容器无法启动，提示端口被占用**
```bash
# 检查端口占用
sudo netstat -tulpn | grep 3306

# 修改 docker-compose.yml 中的端口映射
# 或停止占用端口的服务
```

### 2. 数据库问题

**问题：数据库连接失败**
```bash
# 检查数据库容器状态
docker-compose ps db

# 检查数据库日志
docker-compose logs db

# 测试数据库连接
docker-compose exec db mysql -u root -p${DB_PASSWORD} -e "SHOW DATABASES;"
```

**问题：数据库初始化失败**
```bash
# 手动进入数据库创建
docker-compose exec db mysql -u root -p${DB_PASSWORD}
CREATE DATABASE IF NOT EXISTS tg2blog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;

# 重新初始化表结构
docker-compose run --rm app python scripts/init_db.py
```

### 3. Telegram 问题

**问题：Session 文件失效**
```bash
# 删除旧的 session 文件
rm -f *.session

# 重新认证
python3 scripts/auth_telegram.py

# 重启容器
docker-compose restart app
```

**问题：无法连接到 Telegram 服务器**
```bash
# 检查网络连接
ping -c 3 149.154.167.50

# 检查防火墙规则
sudo iptables -L

# 如果在国内服务器，可能需要配置代理
# 在 .env 中添加：
# TG_PROXY_HOST=your-proxy-host
# TG_PROXY_PORT=your-proxy-port
```

**问题：频道监听不生效**
```bash
# 检查频道配置
cat .env | grep TG_CHANNELS

# 格式应该是：TG_CHANNELS=@channel1,@channel2
# 确保频道名正确，且机器人已加入频道
```

### 4. WordPress 发布问题

## ✅ 部署检查清单

### 部署前检查

- [ ] 已获取 Telegram API 凭证（api_id 和 api_hash）
- [ ] 已配置 WordPress 应用密码
- [ ] 已准备好监听的 Telegram 频道列表
- [ ] 服务器已安装 Docker 和 Docker Compose
- [ ] 已复制并配置 .env 文件
- [ ] 已完成 Telegram 认证（生成 .session 文件）

### 部署后验证

```bash
# 1. 检查容器状态（应该都是 Up）
docker-compose ps

# 2. 检查 app 容器日志（应该看到"开始监听频道"）
docker-compose logs app | tail -20

# 3. 检查数据库连接
docker-compose exec db mysql -u root -p${DB_PASSWORD} -e "USE tg2blog; SHOW TABLES;"

# 4. 测试 WordPress 连接
docker-compose exec app python -c "
from app.core.config import settings
print(f'WordPress URL: {settings.WP_BASE_URL}')
print(f'WordPress User: {settings.WP_USERNAME}')
"

# 5. 查看监听的频道
docker-compose exec app python -c "
from app.core.config import settings
print(f'监听频道: {settings.TG_CHANNELS}')
"
```

### 功能测试

1. **测试消息监听：**
   - 在监听的 Telegram 频道发送测试消息
   - 查看 app 日志是否有接收记录
   ```bash
   docker-compose logs -f app
   ```

2. **测试数据库写入：**
   ```bash
   docker-compose exec db mysql -u root -p${DB_PASSWORD} -e "
   USE tg2blog;
   SELECT COUNT(*) FROM tg_messages;
   SELECT COUNT(*) FROM resources;
   "
   ```

3. **测试 WordPress 发布：**
   - 检查 WordPress 后台是否有新文章
   - 访问文章页面确认跳转链接正常

### 性能监控

```bash
# 查看容器资源占用
docker stats

# 查看数据库大小
docker-compose exec db mysql -u root -p${DB_PASSWORD} -e "
SELECT
  table_schema AS 'Database',
  ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)'
FROM information_schema.tables
WHERE table_schema = 'tg2blog'
GROUP BY table_schema;
"

# 查看日志文件大小
docker-compose exec app du -sh /var/log/*.log 2>/dev/null || echo "日志在容器内部"
```

## 🔄 日常运维

### 定期检查（建议每周）

```bash
# 1. 检查服务状态
docker-compose ps

# 2. 查看最近错误日志
docker-compose logs app | grep -i error | tail -20

# 3. 检查数据库大小
docker-compose exec db mysql -u root -p${DB_PASSWORD} -e "
SELECT COUNT(*) as total_messages FROM tg2blog.tg_messages;
SELECT COUNT(*) as total_resources FROM tg2blog.resources;
SELECT COUNT(*) as total_articles FROM tg2blog.articles;
"

# 4. 备份数据库
docker-compose exec db mysqldump -u root -p${DB_PASSWORD} tg2blog | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 更新部署

```bash
# 1. 拉取最新代码
git pull

# 2. 备份数据库
docker-compose exec db mysqldump -u root -p${DB_PASSWORD} tg2blog > backup_before_update.sql

# 3. 停止服务
docker-compose down

# 4. 重新构建
docker-compose build

# 5. 启动服务
docker-compose up -d

# 6. 查看日志确认正常
docker-compose logs -f app
```

## 📞 监控告警

建议配置监控工具（如 Prometheus + Grafana）监控：
- 容器运行状态
- 数据库连接数
- 消息处理速度
- WordPress 发布成功率
