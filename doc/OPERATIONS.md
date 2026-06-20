# 运维手册

## 1. 日志规范

所有日志使用中文描述 + emoji 前缀，方便 `docker logs` 快速扫描。

### 格式

```
[时间] LEVEL emoji 描述 | 关键字段=值
```

### 日志级别与 emoji 对照

| 场景 | 级别 | emoji | 示例 |
|------|------|-------|------|
| 服务启动完成 | INFO | 🚀 | `🚀 服务启动完成 | 监听频道=2个` |
| 收到新消息 | INFO | 📨 | `📨 收到消息 | 频道=@Oscar_4Kmovies msg_id=12345` |
| 广告过滤跳过 | INFO | 🚫 | `🚫 广告过滤跳过 | msg_id=12345 原因=含t.me链接` |
| 解析成功 | DEBUG | 🔍 | `🔍 解析完成 | 片名=太平年 EP=24 hash=太平年_2026_4k` |
| 解析失败跳过 | WARN | ⚠️ | `⚠️ 解析失败 | msg_id=12345 原因=无法提取片名` |
| 图片下载 | DEBUG | 🖼️ | `🖼️ 图片下载 | 数量=2 耗时=1.2s` |
| 图片上传 | DEBUG | ☁️ | `☁️ 图片上传图床 | url=https://...` |
| 图片复用 | DEBUG | ♻️ | `♻️ 图片复用 | hash匹配 url=https://...` |
| TMDB 命中 | DEBUG | 🎬 | `🎬 TMDB匹配 | 片名=太平年 得分=90 id=12345` |
| TMDB 未命中 | DEBUG | 🎬 | `🎬 TMDB无匹配 | 得分不足60，降级纯TG发文` |
| 新发文章 | INFO | ✅ | `✅ 发布成功 | 《太平年》EP24 cid=100 url=https://...` |
| 更新文章 | INFO | 🔄 | `🔄 更新成功 | 《太平年》EP24→EP25 cid=100` |
| 内容无变化 | DEBUG | ⏭️ | `⏭️ 内容未变化，跳过更新 | hash=太平年_2026_4k` |
| 发布失败 | ERROR | ❌ | `❌ 发布失败 | 片名=太平年 重试=1/3 错误=XMLRPC timeout` |
| 重试成功 | INFO | ✅ | `✅ 重试成功 | 片名=太平年 已等待2分钟` |
| 彻底失败 | ERROR | 💀 | `💀 彻底放弃 | 片名=太平年 已重试3次，转人工处理` |
| catch-up | INFO | ⏪ | `⏪ 补偿历史消息 | 频道=@Oscar_4Kmovies 发现=15条未处理` |
| 启动失败 | ERROR | 🔴 | `🔴 启动失败 | 缺少必要配置: TG_API_ID, TYPECHO_USER` |

---

## 2. 飞书告警

使用飞书自定义机器人 Webhook，消息格式为纯文本（text 类型）。

### 消息模板

**发布成功**（`NOTIFY_ON_SUCCESS=true` 时发送）：
```
✅ 发布成功
片名：《太平年》EP25
链接：https://b.zhuiju.us/tai-ping-nian-2026-4k.html
频道：@Oscar_4Kmovies
```

**发布失败**（必发）：
```
🚨 发布失败
片名：《太平年》
错误：XMLRPC connection timeout
重试：2 / 3，下次重试：5分钟后
```

**彻底失败**（必发）：
```
❌ 已彻底放弃
片名：《太平年》
已重试 3 次，均失败
最后错误：XMLRPC auth failed
请人工检查 Typecho 服务是否正常
```

### 飞书 Webhook 请求格式

```json
POST {FEISHU_WEBHOOK}
Content-Type: application/json

{
  "msg_type": "text",
  "content": {
    "text": "消息内容"
  }
}
```

---

## 3. 重试策略

| 重试次数 | 等待时间 | 状态 |
|---------|---------|------|
| 第1次失败 | 立即标记，2分钟后重试 | failed |
| 第2次失败 | 4分钟后重试 | failed |
| 第3次失败 | 8分钟后重试 | failed |
| 第3次仍失败 | 不再重试 | dead |

- `next_retry_at = now + 2^retry_count 分钟`
- `retry scanner` 每5分钟扫描一次 `status=failed AND next_retry_at <= now`
- `dead` 状态记录需人工介入（检查 Typecho 服务、XMLRPC 配置）

---

## 4. catch-up 机制

**触发时机**：服务启动时，自动执行一次。

**逻辑**：
```
对每个监听频道：
  1. 查询 tg_messages 表，获取该频道最大 msg_id（last_id）
  2. 计算截止时间：now - catchup_hours（默认24小时）
  3. 拉取 TG 频道从 last_id 之后、截止时间之内的历史消息
  4. 逐条入队处理（走完整 pipeline）
  5. 日志：⏪ 补偿历史消息 | 频道=xxx 发现=N条
```

**注意**：如果是全新部署（last_id=0），catch-up 只处理最近24小时消息，不会拉取频道全部历史。

---

## 5. Docker 运维

### 常用命令

```bash
# 启动服务
docker-compose up -d

# 查看实时日志（过滤关键字）
docker-compose logs -f tg2blog

# 只看错误日志
docker-compose logs tg2blog | grep "❌\|🚨\|💀"

# 重启服务
docker-compose restart tg2blog

# 停止服务
docker-compose down

# 查看数据库（需要容器内执行）
docker exec -it tg2blog sqlite3 /data/db/tg2blog.sqlite \
  "SELECT hash_key, status, retry_count FROM content_posts ORDER BY updated_at DESC LIMIT 20;"
```

### 数据目录备份

```bash
# SQLite 备份（服务运行中也可执行，SQLite WAL 模式安全）
cp ./data/db/tg2blog.sqlite ./backup/tg2blog-$(date +%Y%m%d).sqlite
```

---

## 6. 常见问题排查

| 现象 | 排查步骤 |
|------|---------|
| 服务启动失败 | 查日志 `🔴 启动失败`，确认 .env 必填项已填写 |
| TG 消息未收到 | 确认账号已加入频道；重启后 catch-up 会补偿 |
| 文章重复发布 | 检查 `tg_messages` 表的 UNIQUE 约束是否正常 |
| Typecho 发布失败 | 确认 XMLRPC Endpoint 可访问；Typecho 后台已开启 XMLRPC |
| 图片不显示 | 检查 ImgBed 服务状态；文章内 img src 是否为完整 URL |
| TMDB 总是未命中 | 检查 `TMDB_API_TOKEN` 是否有效；`TMDB_SCORE_MIN` 可适当调低 |
| 飞书收不到通知 | 确认 `FEISHU_WEBHOOK` 填写正确；检查飞书机器人是否启用 |
