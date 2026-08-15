-- ============================================================================
-- Typecho 存量重复文章清理 —— 方案 2「合并」
--
-- 背景：存量重复的主因是 Typecho 1.3.0 的 metaWeblog.editPost 根本不更新——它绕过
--       prepare()，$this->cid 恒空，EditTrait::publish() 里 have() 恒 false，于是每次
--       「更新」都 insert() 出一篇新文章（详见 app/publish.py replace_post 的 docstring
--       与 CLAUDE.md「更新文章 = 删旧建新」）。次因是 hash_key 在 AI 与正则两条解析
--       路径间漂移，旧的单向 repo.get_post 查不到历史记录而重复建文。
--       结果 16552 篇文章里只有 10808 部影片，5744 篇是重复。
--       代码侧两处都已止血（publish.replace_post 删旧建新 + repo.find_post 双向匹配），
--       本脚本处理的是存量。
--
-- ⚠️ 两台机器，别搞混：
--      VM116739       → tg2blog 容器；SQLite 在宿主机 /home/tg2blog/data/db/tg2blog.sqlite
--      141.11.77.151  → 宝塔 + Typecho + MySQL b_zhuiju_us（本文件的 SQL 在这里跑）
--
-- ── 为什么是「合并」而不是只改 MySQL ────────────────────────────────────────
-- SQLite 的 content_posts 有 10897 个 cid，但只覆盖 10756 个影片分组：141 个 cid
-- 是同一部影片裂成多行、各持一个 cid 的产物（101 组 2 个、17 组 3 个、2 组 4 个）。
-- 若只在 MySQL 把败者转 private 而不动 SQLite，tg2blog 会继续拿着败者 cid 去
-- replace_post —— 删掉一篇隐藏文章、再新建一篇，站上文章数不减反增，而真正公开的
-- 那篇（胜者）从此再也拿不到更新。所以必须同时把 SQLite 里败者行的
-- typecho_cid 改指向胜者。
--
-- content_posts.typecho_cid 没有 UNIQUE 约束（见 app/db.py），允许多行共享同一个
-- cid，因此这是「改指向」而非「删行」，不丢任何数据，可逐行回滚。
--
-- ── 执行顺序：先 SQLite，后 MySQL。顺序不能反 ──────────────────────────────
--   阶段 0  双侧备份
--   阶段 1  MySQL 只读：算出胜者 / 败者，导出映射
--   阶段 2  VM116739：SQLite 回写 141 行（此时败者文章仍公开，风险为零）
--   阶段 3  MySQL 写：败者及其余重复转 private
--   阶段 4  验证
--   阶段 5  回滚
-- 反过来先转 private 的话，阶段 2 之前的窗口里 tg2blog 会往隐藏文章写更新。
--
-- ── 分组依据 ────────────────────────────────────────────────────────────────
-- REGEXP_REPLACE(slug, '[-_][0-9]+$', '')。tg2blog 的 slug 格式是 {拼音}-{年份}-4k，
-- 永远以 "4k" 结尾、绝不以数字结尾；结尾的 -1 / -2 只可能是 Typecho 遇到 slug
-- 冲突时自己加的后缀。所以这个正则剥掉的一定是冲突后缀，不会误并两部不同影片。
-- 需要 MySQL 8.0。
-- ============================================================================


-- ── 排序规则：所有临时表必须显式 COLLATE=utf8mb4_general_ci ────────────────
-- typecho_contents 是老 Typecho schema 的 utf8mb4_general_ci，而 MySQL 8 建表
-- 默认是 utf8mb4_0900_ai_ci。两者比较会直接报
--   ERROR 1267 Illegal mix of collations
-- 而且即使不报错（如主键去重这类单表内部操作），也会出现「窗口函数按 general_ci
-- 分组、主键按 0900_ai_ci 去重」的双标准。纯 ASCII 拼音 slug 下两者结果一致，
-- 但存量里可能有非 ASCII slug，不能赌。
-- ============================================================================


-- ── 阶段 0：备份（两侧都要，缺一不可）────────────────────────────────────────
--
-- MySQL（141.11.77.151）：
--   mysqldump -u root -p --single-transaction b_zhuiju_us > /root/b_zhuiju_us_$(date +%F).sql
--   ls -lh /root/b_zhuiju_us_*.sql        # 确认不为 0
--
-- SQLite（VM116739）：
--   cd /home/tg2blog
--   cp data/db/tg2blog.sqlite /root/tg2blog_$(date +%F).sqlite
--   ls -lh /root/tg2blog_*.sqlite


-- ══ 阶段 1：MySQL 只读计算 ═══════════════════════════════════════════════════
-- 前置：tg2blog_keep_cid 已从 SQLite 导入，且「悬空 cid」查询返回 0。建表与导入：
--
--   DROP TABLE IF EXISTS tg2blog_keep_cid;
--   CREATE TABLE tg2blog_keep_cid (
--     cid          INT UNSIGNED NOT NULL PRIMARY KEY,
--     hash_key     VARCHAR(255),
--     alt_hash_key VARCHAR(255),
--     sq_status    VARCHAR(32),
--     sq_updated   VARCHAR(64),
--     KEY idx_hash (hash_key)
--   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
--   SOURCE /tmp/keep_cids.sql;
--
-- 导出侧命令见本文件末尾「附：从 SQLite 导出 keep_cids.sql」。
--
-- ⚠️ 下面注释里的期望值是 2026-08-16 那次运行的实测数（keep_cid 10897 行 →
--    胜者 10756+52=10808、败者 141、待private 5744）。tg2blog 一直在跑，每多发
--    一篇文章这些数就会漂移，别把它们当硬断言 —— 真正要卡的是「胜者数 +
--    待private数 = 快照内总数」这个自洽关系，以及「胜者∩败者 = 空集」。

-- 1.1 冻结快照边界。
-- 阶段 3 只处置 cid <= max_cid 的文章。清理期间 tg2blog 仍在运行，新发的文章
-- cid 更大、不在本次 winner 表里，若不设这条边界会被误判为「重复」而转 private。
CREATE TABLE IF NOT EXISTS tg2blog_run_meta (
  k VARCHAR(32)  NOT NULL PRIMARY KEY,
  v BIGINT       NOT NULL
) ENGINE=InnoDB;

REPLACE INTO tg2blog_run_meta (k, v)
SELECT 'max_cid', MAX(cid) FROM typecho_contents WHERE type='post';

SELECT v AS 快照边界max_cid FROM tg2blog_run_meta WHERE k='max_cid';


-- 1.2 胜者表：每个 base_slug 恰好一个 cid（base_slug 做主键，结构上即保证唯一）
DROP TABLE IF EXISTS tg2blog_winner;
CREATE TABLE tg2blog_winner (
  base_slug VARCHAR(255) NOT NULL PRIMARY KEY,
  cid       INT UNSIGNED NOT NULL,
  src       VARCHAR(16)  NOT NULL,   -- sqlite = 有 SQLite 记录；modified = 退化判定
  KEY idx_cid (cid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- 1.2a SQLite 覆盖的分组（10756 组）。判定优先级：
--      ① 持有干净 slug（slug = base_slug）优先 —— 这是被搜索引擎收录的规范链接，
--         也是 worker 一直写进 content_posts.url / 推给飞书的那个 URL（worker 里
--         url 恒按 render 出的干净 slug 计算，与文章实际拿到的 -1/-2 后缀无关）。
--         保它公开，SEO 不断档。代价是这篇通常是组里最早、内容最旧的一篇，靠
--         阶段 2 清空 content_hash 让下一条消息把它刷新；已停更的剧会停在旧集数。
--      ② 非 dead 优先（dead 记录对应的文章 tg2blog 已放弃维护）
--      ③ sq_updated 最新 —— tg2blog 最近一次真正写过的那篇，最可能是活跃的
--      ④ cid 大者（并列时取较新建的）
--      sq_updated 是 now_iso() 产出的固定格式 UTC ISO8601（恒带 +00:00 后缀），
--      按字符串降序排即等于按时间降序排。
INSERT INTO tg2blog_winner (base_slug, cid, src)
SELECT base_slug, cid, 'sqlite' FROM (
  SELECT REGEXP_REPLACE(c.slug,'[-_][0-9]+$','') AS base_slug,
         k.cid,
         ROW_NUMBER() OVER (
           PARTITION BY REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
           ORDER BY (c.slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')) DESC,
                    (k.sq_status='dead') ASC, k.sq_updated DESC, k.cid DESC
         ) AS rn
  FROM tg2blog_keep_cid k
  JOIN typecho_contents c ON c.cid = k.cid AND c.type='post'
) t WHERE rn = 1;

-- 1.2b SQLite 没覆盖的分组（52 组，历史遗留 / 手工发布）→ 同样干净 slug 优先，
--      其次 modified 最新。INSERT IGNORE + base_slug 主键：已有胜者的组自动跳过。
INSERT IGNORE INTO tg2blog_winner (base_slug, cid, src)
SELECT base_slug, cid, 'modified' FROM (
  SELECT REGEXP_REPLACE(c.slug,'[-_][0-9]+$','') AS base_slug,
         c.cid,
         ROW_NUMBER() OVER (
           PARTITION BY REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
           ORDER BY (c.slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')) DESC,
                    c.modified DESC, c.cid DESC
         ) AS rn
  FROM typecho_contents c
  WHERE c.type='post' AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
) t WHERE rn = 1;


-- 1.3 败者映射：SQLite 记着、但不是本组胜者的 cid → 需要在 SQLite 侧改指向
DROP TABLE IF EXISTS tg2blog_loser_map;
CREATE TABLE tg2blog_loser_map (
  loser_cid  INT UNSIGNED NOT NULL PRIMARY KEY,
  winner_cid INT UNSIGNED NOT NULL,
  hash_key   VARCHAR(255) NOT NULL,
  base_slug  VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO tg2blog_loser_map (loser_cid, winner_cid, hash_key, base_slug)
SELECT k.cid, w.cid, k.hash_key, w.base_slug
FROM tg2blog_keep_cid k
JOIN typecho_contents c ON c.cid = k.cid AND c.type='post'
JOIN tg2blog_winner   w ON w.base_slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
WHERE k.cid <> w.cid;


-- ── 1.4 只读检查：1.4.1–1.4.7 全过才能进入阶段 2 ────────────────────────────

-- 1.4.1 胜者来源分布      期望：sqlite=10756  modified=52  合计=10808
SELECT src, COUNT(*) AS 组数 FROM tg2blog_winner GROUP BY src WITH ROLLUP;

-- 1.4.2 败者数量          期望：141
SELECT COUNT(*) AS 败者数 FROM tg2blog_loser_map;

-- 1.4.3 总量自洽          期望：胜者 10808 + 待private 5744 = 文章总数 16552
SELECT
  (SELECT COUNT(*) FROM typecho_contents
     WHERE type='post' AND cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid'))  AS 快照内文章总数,
  (SELECT COUNT(*) FROM tg2blog_winner)                                                AS 胜者数,
  (SELECT COUNT(*) FROM typecho_contents c
     WHERE c.type='post' AND c.status='publish'
       AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
       AND c.cid NOT IN (SELECT cid FROM tg2blog_winner))                              AS 待private数;

-- 1.4.4 胜者与败者不得有交集    期望：Empty set（有输出说明分组逻辑有 bug，停）
SELECT l.loser_cid FROM tg2blog_loser_map l
JOIN tg2blog_winner w ON w.cid = l.loser_cid;

-- 1.4.5 人工过目：≥3 个 cid 的 19 组，看胜者选得对不对
SELECT REGEXP_REPLACE(c.slug,'[-_][0-9]+$','') AS base_slug,
       k.cid, c.slug, c.title, k.sq_status, k.sq_updated,
       CASE WHEN w.cid = k.cid THEN '✅ 胜者' ELSE '→ 转private' END AS 处置
FROM tg2blog_keep_cid k
JOIN typecho_contents c ON c.cid = k.cid AND c.type='post'
JOIN tg2blog_winner   w ON w.base_slug = REGEXP_REPLACE(c.slug,'[-_][0-9]+$','')
WHERE w.base_slug IN (
  SELECT base_slug FROM (
    SELECT REGEXP_REPLACE(c2.slug,'[-_][0-9]+$','') AS base_slug, COUNT(*) AS n
    FROM tg2blog_keep_cid k2
    JOIN typecho_contents c2 ON c2.cid = k2.cid AND c2.type='post'
    GROUP BY base_slug HAVING n >= 3
  ) x
)
ORDER BY base_slug, k.sq_updated DESC;


-- 1.4.6 残留检查：还有多少组的胜者拿的不是干净 slug？
--       1.2a/1.2b 已把干净 slug 排在首位，但 1.2a 的候选集只有 tg2blog_keep_cid
--       里的 cid（硬约束：保留哪一篇以 SQLite 的 typecho_cid 为准）。若某组的干净
--       slug 那篇根本不在 SQLite 里，1.2a 只能在后缀 slug 中选，而该组已有胜者，
--       1.2b 的 INSERT IGNORE 也补不上 —— 这些组的规范链接仍会转 private。
--       期望：'胜者持后缀slug' 为 0 或极小。数量大的话先停下来讨论要不要放宽
--       候选集（改成允许选 SQLite 未收录的干净 slug 篇，阶段 2 一并 repoint 过去）。
SELECT CASE WHEN c.slug = w.base_slug THEN '胜者持干净slug' ELSE '胜者持后缀slug' END AS 情况,
       w.src,
       COUNT(*) AS 组数
FROM tg2blog_winner w
JOIN typecho_contents c ON c.cid = w.cid AND c.type='post'
GROUP BY 1, 2;

-- 1.4.7 列出上面「胜者持后缀slug」的组，逐个看（上限 50 行）
SELECT w.base_slug, w.cid AS 胜者cid, c.slug AS 胜者slug, w.src,
       (SELECT c2.cid FROM typecho_contents c2
         WHERE c2.type='post' AND c2.slug = w.base_slug LIMIT 1) AS 干净slug所属cid
FROM tg2blog_winner w
JOIN typecho_contents c ON c.cid = w.cid AND c.type='post'
WHERE c.slug <> w.base_slug
LIMIT 50;


-- 1.5 导出败者映射，供阶段 2 使用（在 141 的 shell 里执行，不是 mysql 提示符）
--   /www/server/mysql/bin/mysql -u b_zhuiju_us -p b_zhuiju_us -B \
--     -e "SELECT loser_cid, winner_cid, hash_key FROM tg2blog_loser_map" > /tmp/loser_map.tsv
--   wc -l /tmp/loser_map.tsv        # 应为 142（1 行表头 + 141 行数据）
--
-- 然后在 VM116739 上拉取（公钥方向是 VM116739 → 141，所以用 pull 而非 push）：
--   scp root@141.11.77.151:/tmp/loser_map.tsv /tmp/


-- ══ 阶段 2：SQLite 回写（在 VM116739 执行，见 sqlite_repoint_losers.py）══════
--
--   cd /home/tg2blog
--   docker compose stop tg2blog          # 避免与串行消费者抢写锁；停机期间漏掉的
--                                        # 消息由启动 catch-up 补回
--   python3 doc/sql/sqlite_repoint_losers.py --tsv /tmp/loser_map.tsv --dry-run
--   python3 doc/sql/sqlite_repoint_losers.py --tsv /tmp/loser_map.tsv --apply
--   docker compose start tg2blog
--
-- 脚本会先把 (hash_key, 原 typecho_cid, 原 content_hash) 存进 SQLite 的
-- tg2blog_dedup_backup 表，再把 typecho_cid 改指向胜者、content_hash 置空。
-- 置空 content_hash 是为了让下一条消息真正推一次更新到胜者文章 —— 否则败者 key
-- 会因指纹未变而在 worker 第 7 步短路，胜者文章拿不到最新内容。


-- ══ 阶段 3：MySQL 转 private（阶段 2 完成后才执行）═══════════════════════════
-- 用 'private' 而非 'hidden'：部分 Typecho 版本下 hidden 的直链仍可访问，
-- 达不到从搜索引擎移除重复内容的目的。

CREATE TABLE IF NOT EXISTS tg2blog_dedup_backup (
  cid        INT UNSIGNED NOT NULL PRIMARY KEY,
  slug       VARCHAR(255),
  title      VARCHAR(255),
  old_status VARCHAR(32),
  modified   INT,
  backed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT IGNORE INTO tg2blog_dedup_backup (cid, slug, title, old_status, modified)
SELECT c.cid, c.slug, c.title, c.status, c.modified
FROM typecho_contents c
WHERE c.type='post'
  AND c.status='publish'
  AND c.cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
  AND c.cid NOT IN (SELECT cid FROM tg2blog_winner);

-- 必须等于 1.4.3 的「待private数」，不等就停
SELECT COUNT(*) AS 已备份行数 FROM tg2blog_dedup_backup;

UPDATE typecho_contents c
JOIN tg2blog_dedup_backup b ON b.cid = c.cid
SET c.status = 'private'
WHERE c.status = 'publish';


-- ══ 阶段 4：验证 ═════════════════════════════════════════════════════════════

-- 4.1 状态分布      期望：publish ≈ 10808（含清理期间新发的），private ≈ 5744
SELECT status, COUNT(*) FROM typecho_contents WHERE type='post' GROUP BY status;

-- 4.2 公开文章里还有没有重复      期望：Empty set
SELECT REGEXP_REPLACE(slug,'[-_][0-9]+$','') AS base_slug, COUNT(*) AS n
FROM typecho_contents
WHERE type='post' AND status='publish'
  AND cid <= (SELECT v FROM tg2blog_run_meta WHERE k='max_cid')
GROUP BY base_slug HAVING n > 1 LIMIT 10;

-- 4.3 最关键：SQLite 现在指向的每一个 cid，在 MySQL 里都必须是 publish。
--     有输出 = tg2blog 正在更新一篇隐藏文章，立刻回滚阶段 3。
--     需重新导出 SQLite 的 cid 清单后再跑（见下方 4.3 前置）。
-- 4.3 前置（VM116739）：
--   docker compose exec -T tg2blog python -c "import sqlite3;print(','.join(str(x[0]) for x in sqlite3.connect('/data/db/tg2blog.sqlite').execute('SELECT DISTINCT typecho_cid FROM content_posts WHERE typecho_cid IS NOT NULL')))" > /tmp/live_cids.txt
--   scp 到 141 后：
SELECT c.cid, c.slug, c.status
FROM typecho_contents c
JOIN tg2blog_keep_cid_v2 v ON v.cid = c.cid
WHERE c.type='post' AND c.status <> 'publish';
-- （tg2blog_keep_cid_v2 = 重新导入的最新 SQLite cid 清单，建表方式同 tg2blog_keep_cid）

-- 4.4 浏览器验证（退出登录或用无痕窗口）：
--   取一个被转 private 的 slug，访问 https://b.zhuiju.us/archives/<slug>.html
--   应返回 404。仍能访问说明该 Typecho 版本的 private 语义不同，换状态重试。

-- 4.5 Typecho 后台 → 设置 → 保存一次（或清缓存插件），让分类/标签计数重新统计。


-- ══ 阶段 5：回滚 ═════════════════════════════════════════════════════════════
--
-- MySQL 全量恢复（阶段 3）：
--   UPDATE typecho_contents c
--     JOIN tg2blog_dedup_backup b ON b.cid = c.cid
--     SET c.status = b.old_status;
--
-- MySQL 单篇恢复：
--   UPDATE typecho_contents SET status='publish' WHERE cid = <某个cid>;
--
-- SQLite 回滚（阶段 2）：
--   python3 doc/sql/sqlite_repoint_losers.py --rollback
--
-- 两侧回滚互相独立，可以只回滚一侧。若只回滚 MySQL 而保留 SQLite 的改指向，
-- 结果等价于「方案 1 保守」：站上残留 141 篇重复，但 tg2blog 已收敛到单篇维护。
--
-- 确认无误后清理临时表（占用极小，建议保留至少一个月）：
--   DROP TABLE tg2blog_keep_cid;
--   DROP TABLE tg2blog_winner;
--   DROP TABLE tg2blog_loser_map;
--   DROP TABLE tg2blog_run_meta;
--   DROP TABLE tg2blog_dedup_backup;


-- ══ 附：从 SQLite 导出 keep_cids.sql（在 VM116739 执行）═══════════════════════
--
-- 生成一份 INSERT 语句文件，再 scp 到 141 用 SOURCE 导入 tg2blog_keep_cid。
-- 容器不必停 —— 这一步纯读。但导出与阶段 1 之间隔得越久，快照越容易漂移，
-- 建议导出后立刻做阶段 1。
--
--   cd /home/tg2blog
--   python3 - <<'PY'
--   import sqlite3
--   conn = sqlite3.connect("data/db/tg2blog.sqlite")
--   rows = conn.execute("""
--       SELECT typecho_cid, hash_key, COALESCE(alt_hash_key,''),
--              status, updated_at
--       FROM content_posts
--       WHERE typecho_cid IS NOT NULL AND typecho_cid > 0
--   """).fetchall()
--   def q(s):
--       return "'" + str(s).replace("\\", "\\\\").replace("'", "''") + "'"
--   # 显式 encoding="utf-8" 写文件，不要用 print + shell 重定向：sys.stdout 的编码
--   # 跟随 locale，LANG=C 时会 UnicodeEncodeError 直接崩，GBK 环境下更糟——静默写出
--   # 乱码，MySQL 按 utf8mb4 读进来就是一堆废 hash_key，而且要到阶段 1 才发现。
--   with open("/tmp/keep_cids.sql", "w", encoding="utf-8", newline="\n") as fh:
--       fh.write("SET NAMES utf8mb4;\n")
--       fh.write("TRUNCATE TABLE tg2blog_keep_cid;\n")
--       # 分批 INSERT，单条语句别撑爆 max_allowed_packet
--       for i in range(0, len(rows), 500):
--           vals = ",".join(
--               "(%d,%s,%s,%s,%s)" % (r[0], q(r[1]), q(r[2]), q(r[3]), q(r[4]))
--               for r in rows[i:i+500]
--           )
--           fh.write("INSERT IGNORE INTO tg2blog_keep_cid "
--                    "(cid,hash_key,alt_hash_key,sq_status,sq_updated) "
--                    "VALUES %s;\n" % vals)
--       fh.write("-- rows exported: %d\n" % len(rows))
--   print("rows exported:", len(rows))
--   PY
--
--   tail -1 /tmp/keep_cids.sql          # 记下 rows exported，阶段 1 要对得上
--   file /tmp/keep_cids.sql             # 应含 UTF-8，不能是 ISO-8859 / unknown
--   grep -c '^INSERT' /tmp/keep_cids.sql
--
-- ⚠️ INSERT IGNORE 而非 INSERT：cid 是主键，而 content_posts 允许多个 hash_key
--    共享同一个 typecho_cid（没有 UNIQUE 约束，阶段 2 的改指向正是这么做的）。
--    重复 cid 被忽略即可 —— keep_cid 只用来回答「这个 cid 是否被 SQLite 记着」，
--    以及提供选胜者用的 sq_status / sq_updated。因此 rows exported 可能大于
--    tg2blog_keep_cid 的最终行数，两者不等不是错误。
--
-- 推到 141（公钥方向是 VM116739 → 141）：
--   scp /tmp/keep_cids.sql root@141.11.77.151:/tmp/
--
-- 在 141 上按阶段 1 抬头的 DDL 建表后：
--   SOURCE /tmp/keep_cids.sql;
--   SELECT COUNT(*) FROM tg2blog_keep_cid;
--
-- 悬空 cid 检查（阶段 1 的前置条件，期望 0）：
--   SELECT COUNT(*) AS 悬空cid数 FROM tg2blog_keep_cid k
--   LEFT JOIN typecho_contents c ON c.cid = k.cid AND c.type='post'
--   WHERE c.cid IS NULL;
-- 不为 0 说明 SQLite 指向了 MySQL 里已不存在的文章（历史手工删除，或删旧建新
-- 时删成功建失败）。这些行不影响胜负判定（JOIN 会自然排除），但值得记一笔。
