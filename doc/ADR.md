# 架构决策记录（ADR）

记录关键技术决策的背景、选项和最终选择，供后续维护参考。

---

## ADR-001：TG 监听方案 — Telethon vs Bot API

**背景**：需要监听第三方影视频道（非自己管理的频道）的消息。

**选项**：
- Telethon（用户账号 MTProto 协议）
- python-telegram-bot（Bot API）

**决策**：选择 **Telethon**

**原因**：Bot API 只能接收 Bot 被主动添加到的群/频道的消息；要监听任意公开频道（如 @Oscar_4Kmovies），必须用用户账号。Telethon 直接使用 MTProto 协议，支持用户账号监听任意公开频道，并可拉取历史消息（catch-up）。

**风险**：用户账号监听有被 TG 封号的小概率风险。缓解措施：不频繁切换频率，session 持久化，不模拟异常操作。

---

## ADR-002：并发模型 — asyncio.Queue 串行 vs 多线程/多进程

**背景**：多个 TG 频道可能同时推送消息，需要安全并发处理。

**选项**：
- asyncio.Queue + 单消费者协程（串行）
- asyncio.Queue + 多消费者协程（并发）
- threading.Thread

**决策**：选择 **asyncio.Queue + 单消费者（串行）**

**原因**：同一部影视（同一 hash_key）可能在短时间内收到多条消息（EP 更新），并发处理会产生竞争条件（两个协程都判断文章不存在，各自发布一篇重复文章）。串行队列从根本上消除并发冲突，代码更简单，无需锁。日均消息量百级，串行处理完全满足性能需求。

---

## ADR-003：存储 — SQLite vs PostgreSQL

**背景**：需要持久化消息去重、发布状态、TMDB 缓存。

**选项**：
- SQLite
- PostgreSQL

**决策**：选择 **SQLite**

**原因**：单机 Docker 部署，无需独立数据库服务，数据文件直接挂载到宿主机，备份简单（复制文件即可）。日均消息量百级，SQLite 读写性能远超需求。未来如果需要多实例横向扩展，再迁移到 PostgreSQL。

---

## ADR-004：Typecho 集成 — XMLRPC vs 直连数据库

**背景**：需要向 Typecho 发布和更新文章。

**选项**：
- Typecho XMLRPC（MetaWeblog API）
- 直连 Typecho MySQL 数据库

**决策**：选择 **XMLRPC**

**原因**：直连数据库耦合度极高，Typecho 升级或改表结构会直接导致系统崩溃；且直连数据库绕过 Typecho 的内部逻辑（缓存清理、钩子、插件），可能导致功能异常。XMLRPC 是 Typecho 官方支持的接口，向前兼容性好，1.3.0 已验证可用。

---

## ADR-005：消息解析策略 — 通用解析器 vs 按频道配置

**背景**：监听多个频道，各频道消息格式有差异。

**选项**：
- 一套通用解析器，覆盖所有格式变体
- 每个频道单独配置解析规则

**决策**：选择 **通用解析器 + 双层 fallback**

**原因**：维护多套 channel-specific 规则成本高，每新增频道都需要调整代码。通用解析器用"第一层严格正则 + 第二层宽松 fallback"覆盖大多数变体，完全无法解析时降级保留原始标题发文（而非丢弃消息），确保覆盖率最大化。后续如有必要，可在 `parse.py` 内以 channel 作为 context 参数传入，实现最小代价的 per-channel 微调。

---

## ADR-006：Slug 生成 — pypinyin vs hash vs URL-encoded

**背景**：Typecho 文章需要 SEO 友好的 URL slug。

**选项**：
- pypinyin 生成拼音 slug（如 `tai-ping-nian-2026-4k`）
- md5[:8] 哈希 slug（如 `a1b2c3d4-2026-4k`）
- URL-encoded 中文（如 `%E5%A4%AA%E5%B9%B3%E5%B9%B4-2026-4k`）

**决策**：选择 **pypinyin**

**原因**：拼音 slug 对搜索引擎友好，且对运维人员可读（可从 URL 判断是哪部影视）。URL-encoded 中文在部分场景下显示为乱码，SEO 效果差，明确排除。哈希 slug 作为不能安装 pypinyin 时的最终备用。

---

## ADR-007：通知渠道 — 飞书 vs Telegram Bot vs 邮件

**背景**：需要运维告警通知（发布失败等）。

**选项**：
- 飞书 Webhook
- Telegram Bot（自建 Bot 反向通知）
- 邮件

**决策**：选择 **飞书 Webhook**

**原因**：用户已有飞书使用习惯，Webhook 接入零运维成本（无需额外 Bot 账号），消息即时推送。TG Bot 虽然也可行，但增加一个 TG 账号管理负担；邮件实时性差。
