# 测试计划

## 测试策略

- **parse.py**：单元测试覆盖所有解析变体（可离线执行，无外部依赖）
- **filter.py**：单元测试关键词 + 链接检测
- **pipeline 集成测试**：Mock 所有外部服务（TG/ImgBed/TMDB/Typecho），验证完整流程
- **验收测试**：真实环境端到端手动验证

---

## 一、单元测试（parse.py）

每条用例给定一段 TG 原始文本，验证 `parse()` 返回值。

| 用例 | 输入特征 | 期望结果 |
|------|---------|---------|
| T-P-01 | 标准格式：片名+年份+4K+EP+标签+简介 | 全字段正确提取 |
| T-P-02 | 无年份 | `year=""` |
| T-P-03 | EP 格式为"全24集完结" | `episode_num=24, is_series=True` |
| T-P-04 | EP 格式为"第24集" | `episode_num=24, is_series=True` |
| T-P-05 | 电影（无 EP 信息） | `episode_num=0, is_series=False` |
| T-P-06 | 无内容简介区块 | `summary=""` |
| T-P-07 | 无标签 | `tags=[]` |
| T-P-08 | 片名含特殊字符（括号、·） | 正确提取，特殊字符被 normalize 处理 |
| T-P-09 | 纯广告文本，无法提取片名 | 返回 `None` |
| T-P-10 | hash_key 生成 | `太平年_2026_4k`（全小写，无空格） |

---

## 二、单元测试（filter.py）

| 用例 | 输入 | 期望结果 |
|------|------|---------|
| T-F-01 | 含黑名单关键词"推广" | `is_ad=True` |
| T-F-02 | 含 `t.me/` 链接 | `is_ad=True` |
| T-F-03 | 含 `https://t.me/xxx` | `is_ad=True` |
| T-F-04 | 正常影视消息 | `is_ad=False` |
| T-F-05 | 消息中"推广"出现在片名中（如《推广大师》） | 需验证误判率；关键词建议配置更精确 |

---

## 三、集成测试（pipeline，Mock 外部服务）

### T-I-01：基础发文流程

**前提**：全新 SQLite，Mock Typecho 返回 cid=100

**步骤**：
1. 构造一条标准 TG 消息（含 EP24）
2. 执行完整 pipeline

**验收**：
- `tg_messages` 表有记录
- `content_posts` 表有记录，`status=published`，`typecho_cid=100`
- Mock Typecho 的 `newPost` 被调用一次

---

### T-I-02：消息编辑更新（EP24 → EP25）

**步骤**：
1. T-I-01 完成后
2. 构造同一消息的编辑版本（EP25，同 channel + msg_id）
3. 执行 pipeline

**验收**：
- `content_posts` 表只有1条记录（不新增）
- `last_episode_num` 更新为 25
- Mock Typecho 的 `editPost` 被调用（不是 `newPost`）

---

### T-I-03：同一 hash_key 不同 msg_id 去重

**步骤**：
1. 第一条消息（msg_id=100）处理完成
2. 构造 msg_id=101 但 hash_key 相同的消息
3. 执行 pipeline

**验收**：
- `tg_messages` 表有2条记录（msg_id 不同）
- `content_posts` 表只有1条记录（hash_key 唯一）
- Typecho `editPost` 被调用（复用已有 cid）

---

### T-I-04：重复消息去重（完全相同 msg_id）

**步骤**：
1. T-I-01 完成后
2. 再次处理完全相同的消息（同 channel + msg_id）

**验收**：
- Typecho 无任何调用（直接跳过）
- 日志出现 `⏭️ 内容未变化，跳过更新`

---

### T-I-05：ImgBed 失败降级

**步骤**：
1. Mock ImgBed 抛出异常
2. 处理带图片的 TG 消息

**验收**：
- 文章仍然成功发布
- 日志出现图片上传失败提示
- 如果 TMDB 有海报，使用 TMDB 海报；否则无图

---

### T-I-06：TMDB 失败降级

**步骤**：
1. Mock TMDB 抛出异常
2. 处理 TG 消息

**验收**：
- 文章仍然成功发布
- 文章内容仅含 TG 原始信息，无 TMDB 字段
- 无 TMDB attribution

---

### T-I-07：Typecho 发布失败 + 自动重试

**步骤**：
1. Mock Typecho 前2次抛出异常，第3次成功
2. 处理 TG 消息

**验收**：
- 第1次失败：`status=failed, retry_count=1`，飞书收到失败通知
- retry scanner 触发重试
- 第2次失败：`status=failed, retry_count=2`
- 第3次成功：`status=published`，飞书收到成功通知（若 NOTIFY_ON_SUCCESS=true）

---

### T-I-08：彻底失败（3次均失败）

**步骤**：
1. Mock Typecho 始终抛出异常
2. 处理 TG 消息，等待3次重试耗尽

**验收**：
- `status=dead, retry_count=3`
- 飞书收到 `❌ 已彻底放弃` 通知
- retry scanner 不再处理该记录

---

### T-I-09：图片去重复上传

**步骤**：
1. T-I-01 完成后（已有 cover_image_url 和 tg_img_hash）
2. 构造 EP25 编辑消息（图片内容相同）
3. 执行 pipeline

**验收**：
- ImgBed 上传接口未被调用（img_hash 匹配，复用历史 URL）
- 日志出现 `♻️ 图片复用`

---

## 四、验收测试（真实环境端到端）

| 编号 | 测试场景 | 验收标准 |
|------|---------|---------|
| T-E-01 | 真实 TG 消息触发发文 | Typecho 后台可见文章，内容格式正确 |
| T-E-02 | 文章底部网盘链接 | 4个网盘链接 + zhuiju.us 入口均正确渲染 |
| T-E-03 | 文章底部 Q&A 区块 | 正常显示 |
| T-E-04 | slug 为拼音格式 | URL 为拼音，非中文编码 |
| T-E-05 | 关闭 IMGBED_ENABLE | 无图文章正常发布 |
| T-E-06 | 关闭 TMDB_ENABLE | 纯 TG 信息文章正常发布 |
| T-E-07 | 服务重启后 catch-up | 重启后自动补发最近24小时未处理消息 |
| T-E-08 | 广告消息被过滤 | 广告消息不触发发文，日志有 `🚫` 记录 |
| T-E-09 | 飞书通知 | 发布失败时飞书机器人收到告警消息 |
