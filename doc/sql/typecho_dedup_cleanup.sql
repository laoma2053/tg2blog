-- ============================================================================
-- Typecho 存量重复文章清理 —— MySQL 单侧
--
-- ⚠️ 状态：**暂不执行**。已决定不清理历史重复文章，站上那 5744 篇重复保持原样。
--    本文件作为分析结论和随时可用的预案保留，不是待办事项。
--    真要执行时，从阶段 0 开始按顺序走，阶段 1 全程只读、可随时放弃。
--
-- 背景：存量重复的主因是 Typecho 1.3.0 的 metaWeblog.editPost 根本不更新——它绕过
--       prepare()，$this->cid 恒空，EditTrait::publish() 里 have() 恒 false，于是每次
--       「更新」都 insert() 出一篇新文章（根因记录见 CLAUDE.md「不做文章更新」）。
--       次因是 hash_key 在 AI 与正则两条解析路径间漂移，旧的单向 repo.get_post
--       查不到历史记录而重复建文。
--       结果 16552 篇文章里只有 10808 部影片，5744 篇是重复。
--
-- 代码侧已彻底止血：tg2blog 现在**不再更新任何历史文章**，一部影片只发一次
--       （worker 第 1 步拦编辑消息、第 7 步按 typecho_cid 拦已发布影片）。
--       所以存量清完就是清完了，不会再长出新的重复。
--
-- ⚠️ 两台机器，别搞混：
--      VM116739       → tg2blog 容器（本次完全不用动它）
--      141.11.77.151  → 宝塔 + Typecho + MySQL b_zhuiju_us（本文件的 SQL 全在这里跑）
--
-- ── 为什么只改 MySQL，不动 SQLite ──────────────────────────────────────────
-- 早先的版本里有一个「阶段 2：把 SQLite 里败者行的 typecho_cid 改指向胜者」，
-- 理由是 tg2blog 会继续拿着败者 cid 去更新，不改就会更新到一篇隐藏文章上。
-- 改成不做更新之后这个理由消失了：SQLite 的 typecho_cid 只被用来回答「这部影片
-- 发过没有」这一个是非题，指向哪一篇不再有任何影响。
-- 因此阶段 2、配套的 sqlite_repoint_losers.py、以及从 SQLite 导出 keep_cid 的
-- 整套流程都已删除。现在是「MySQL 只读计算 + 一条 UPDATE」，容器不用停。
--
-- ── 执行顺序 ────────────────────────────────────────────────────────────────
--   阶段 0  备份
--   阶段 1  只读：算出胜者，5 项检查
--   阶段 2  写：非胜者转 private
--   阶段 3  验证
--   阶段 4  回滚
--
-- ── 分组依据 ────────────────────────────────────────────────────────────────
-- REGEXP_REPLACE(slug, '[-_][0-9]+$', '')。tg2blog 的 slug 格式是 {拼音}-{年份}-4k，
-- 永远以 "4k" 结尾、绝不以数字结尾；结尾的 -1 / -2 只可能是 Typecho 遇到 slug
-- 冲突时自己加的后缀。所以这个正则剥掉的一定是冲突后缀，不会误并两部不同影片。
-- 需要 MySQL 8.0。
--
-- ── 胜者规则：持有干净 slug 者胜 ────────────────────────────────────────────
-- 干净 slug（slug = base_slug，即没有 -1/-2 后缀的那篇）是被搜索引擎收录的规范
-- 链接，也是 tg2blog 一直写进 content_posts.typecho_url、推给飞书的那个 URL
-- （worker 里 url 恒按 render 出的干净 slug 计算，与文章实际拿到的后缀无关）。
-- 重复组里最早那篇持有它。保它公开，SEO 不断档。
--
-- 原先「保留哪一篇以 SQLite 的 typecho_cid 为准」这条约束，理由是 tg2blog 要继续
-- 更新那一篇；现在谁也不更新了，约束失去了理由，故不再受 SQLite 限制——这也顺带
-- 消除了「干净 slug 那篇不在 SQLite 里就只能转 private」的残留问题。
-- 代价：留下的那篇内容是首发时的旧集数，且不会再被刷新——这是「不做更新」这个
-- 产品决策本身的代价，与清理方案无关。
--
-- ── 排序规则：临时表显式 COLLATE=utf8mb4_general_ci ────────────────────────
-- typecho_contents 是老 Typecho schema 的 utf8mb4_general_ci，而 MySQL 8 建表
-- 默认是 utf8mb4_0900_ai_ci。两者比较会直接报
--   ERROR 1267 Illegal mix of collations
-- 而且即使不报错（如主键去重这类单表内部操作），也会出现「窗口函数按 general_ci
-- 分组、主键按 0900_ai_ci 去重」的双标准。纯 ASCII 拼音 slug 下两者结果一致，
-- 但存量里可能有非 ASCII slug，不能赌。
-- ============================================================================


-- ══ 阶段 0：备份 ═════════════════════════════════════════════════════════════
--
--   mysqldump -u root -p --single-transaction b_zhuiju_us > /root/b_zhuiju_us_$(date +%F).sql
--   ls -lh /root/b_zhuiju_us_*.sql        # 确认不为 0


-- ══ 阶段 1：只读计算 ═════════════════════════════════════════════════════════
-- ⚠️ 下面注释里的期望值是历史某次运行的实测数。tg2blog 一直在跑，每多发一篇文章
--    这些数就会漂移，别把它们当硬断言 —— 真正要卡的是 1.3.2 那个自洽关系。

-- 1.1 冻结快照边界。
-- 阶段 2 只处置 cid <= max_cid 的文章。清理期间 tg2blog 仍在运行，新发的文章
-- cid 更大、不在本次 winner 表里，若不设这条边界会被误判为「重复」而转 private。
CREATE TABLE IF NOT EXISTS tg2blog_run_meta (
  k VARCHAR(32)  NOT NULL PRIMARY KEY,
  v BIGINT       NOT NULL
) ENGINE=InnoDB;

REPLACE INTO tg2blog_run_meta (k, v)
SELECT 'max_cid', MAX(cid) FROM typecho_contents WHERE type='post';

SELECT v AS 快照边界max_cid FROM tg2blog_run_meta WHERE k='max_cid';


-- 1.2 胜者表：每个 base_slug 恰好一个 cid（base_slug 做主键，结构上即保证唯一）
--     判定优先级：
--       ① 持有干净 slug（slug = base_slug）—— 规范链接，保它公开
--       ② modified 最新
--       ③ cid 大者（并列时取较新建的）
--     只看 typecho_contents，不依赖 SQLite。
DROP TABLE IF EXISTS tg2blog_winner;
CREATE TABLE tg2blog_winner (
  base_slug VARCHAR(255) NOT NULL PRIMARY KEY,
  cid       INT UNSIGNED NOT NULL,
  KEY idx_cid (cid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO tg2blog_winner (base_slug, cid)
SELECT base_slug, cid FROM (
  SELECT REGEXP_REPLACE(c.slug,'[-_][0-9]+$','') AS base_slug,
         c.cid,
         ROW_NUMBER() OVER (
           PARTITION BY REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
           ORDER BY (c.slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')) DESC,
                    c.modified DESC, c.cid DESC
         ) AS rn
  FROM typecho_contents c
  WHERE c.type='post'
    AND c.status='publish'
    AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
) t WHERE rn = 1;


-- ── 1.3 只读检查：1.3.1–1.3.5 全过才能进入阶段 2 ────────────────────────────

-- 1.3.1 胜者数（= 去重后的影片数）      参考值：约 10808
SELECT COUNT(*) AS 胜者数 FROM tg2blog_winner;

-- 1.3.2 总量自洽 —— 必须满足：胜者数 + 待private数 = 快照内公开文章总数
--       不相等就停下来，说明分组或边界有问题。
SELECT
  (SELECT COUNT(*) FROM typecho_contents
     WHERE type='post' AND status='publish'
       AND cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid'))          AS 快照内公开总数,
  (SELECT COUNT(*) FROM tg2blog_winner)                                        AS 胜者数,
  (SELECT COUNT(*) FROM typecho_contents c
     WHERE c.type='post' AND c.status='publish'
       AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
       AND c.cid NOT IN (SELECT cid FROM tg2blog_winner))                      AS 待private数;

-- 1.3.3 胜者是否都拿到了干净 slug      期望：'胜者持后缀slug' 为 0
--       不为 0 说明该组里根本没有哪一篇持有干净 slug（干净的那篇早被手工删过），
--       属正常情况，不阻断，但记一笔。
SELECT CASE WHEN c.slug = w.base_slug THEN '胜者持干净slug' ELSE '胜者持后缀slug' END AS 情况,
       COUNT(*) AS 组数
FROM tg2blog_winner w
JOIN typecho_contents c ON c.cid = w.cid AND c.type='post'
GROUP BY 1;

-- 1.3.4 每个 base_slug 只能有一个胜者      期望：Empty set
SELECT base_slug, COUNT(*) FROM tg2blog_winner GROUP BY base_slug HAVING COUNT(*) > 1;

-- 1.3.5 人工过目：重复最多的 20 组，看留下的是不是干净 slug 那篇
SELECT REGEXP_REPLACE(c.slug,'[-_][0-9]+$','') AS base_slug,
       COUNT(*) AS 组内篇数,
       MAX(CASE WHEN c.cid = w.cid THEN c.slug END) AS 留下的slug,
       MAX(CASE WHEN c.cid = w.cid THEN c.cid  END) AS 留下的cid
FROM typecho_contents c
JOIN tg2blog_winner w ON w.base_slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
WHERE c.type='post' AND c.status='publish'
  AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
GROUP BY base_slug
ORDER BY 组内篇数 DESC
LIMIT 20;


-- ══ 阶段 2：转 private ═══════════════════════════════════════════════════════
-- 用 'private' 而非 'hidden'：部分 Typecho 版本下 hidden 的直链仍可访问，
-- 达不到从搜索引擎移除重复内容的目的。

CREATE TABLE IF NOT EXISTS tg2blog_dedup_backup (
  cid        INT UNSIGNED NOT NULL PRIMARY KEY,
  slug       VARCHAR(255),
  title      VARCHAR(255),
  old_status VARCHAR(32),
  modified   INT,
  backed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT IGNORE INTO tg2blog_dedup_backup (cid, slug, title, old_status, modified)
SELECT c.cid, c.slug, c.title, c.status, c.modified
FROM typecho_contents c
WHERE c.type='post'
  AND c.status='publish'
  AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
  AND c.cid NOT IN (SELECT cid FROM tg2blog_winner);

-- 必须等于 1.3.2 的「待private数」，不等就停
SELECT COUNT(*) AS 已备份行数 FROM tg2blog_dedup_backup;

UPDATE typecho_contents c
JOIN tg2blog_dedup_backup b ON b.cid = c.cid
SET c.status = 'private'
WHERE c.status = 'publish';


-- ══ 阶段 3：验证 ═════════════════════════════════════════════════════════════

-- 3.1 状态分布      期望：publish ≈ 胜者数（含清理期间新发的），private ≈ 待private数
SELECT status, COUNT(*) FROM typecho_contents WHERE type='post' GROUP BY status;

-- 3.2 公开文章里还有没有重复      期望：Empty set
SELECT REGEXP_REPLACE(slug,'[-_][0-9]+$','') AS base_slug, COUNT(*) AS n
FROM typecho_contents
WHERE type='post' AND status='publish'
  AND cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
GROUP BY base_slug HAVING n > 1 LIMIT 10;

-- 3.3 每个影片分组至少还留着一篇公开的      期望：Empty set
--     有输出 = 某部影片被整组转 private，站上彻底没了，必须立刻回滚。
SELECT w.base_slug, w.cid
FROM tg2blog_winner w
JOIN typecho_contents c ON c.cid = w.cid
WHERE c.status <> 'publish';

-- 3.4 浏览器验证（退出登录或用无痕窗口）：
--   取一个被转 private 的 slug，访问 https://b.zhuiju.us/archives/<slug>.html
--     → 应返回 404
--   取一个胜者的干净 slug，访问 https://b.zhuiju.us/archives/<base_slug>.html
--     → 应正常打开（这是规范链接，必须还活着）

-- 3.5 Typecho 后台 → 设置 → 保存一次（或清缓存插件），让分类/标签计数重新统计。


-- ══ 阶段 4：回滚 ═════════════════════════════════════════════════════════════
--
-- 全量恢复：
--   UPDATE typecho_contents c
--     JOIN tg2blog_dedup_backup b ON b.cid = c.cid
--     SET c.status = b.old_status;
--
-- 单篇恢复：
--   UPDATE typecho_contents SET status='publish' WHERE cid = <某个cid>;
--
-- 本次不动 SQLite，所以没有第二侧要回滚。
--
-- 确认无误后清理临时表（占用极小，建议保留至少一个月）：
--   DROP TABLE tg2blog_winner;
--   DROP TABLE tg2blog_run_meta;
--   DROP TABLE tg2blog_dedup_backup;
--
-- 若之前的运行留下过这两张表，一并清掉：
--   DROP TABLE IF EXISTS tg2blog_keep_cid;
--   DROP TABLE IF EXISTS tg2blog_loser_map;
