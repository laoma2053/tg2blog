-- ============================================================================
-- Typecho 侧索引优化 —— 针对 tg2blog 自动发文引发的 MySQL 全表扫描
--
-- 背景：tg2blog 从不直连 MySQL，只调用 3 个 XMLRPC 方法
--       （getCategories / newPost / editPost）。performance_schema 里抓到的
--       三条无索引 SQL 全部由 Typecho 核心 PHP 在处理 newPost/editPost 时
--       自己发出，客户端无法规避，只能靠索引消除全表扫描。
--
-- 执行前务必：
--   1) 备份： mysqldump -u root -p b_zhuiju_us > b_zhuiju_us_$(date +%F).sql
--   2) 跑「第 0 步」看清现有索引，已存在同名/同前缀索引则跳过对应语句
--   3) 建议在低峰期执行；下面几张表数据量都很小（万级），ALTER 秒级完成
-- ============================================================================

-- ── 第 0 步：查看现状（先跑这一段，再决定要不要建）────────────────────────
SHOW INDEX FROM b_zhuiju_us.typecho_contents;
SHOW INDEX FROM b_zhuiju_us.typecho_metas;
SHOW INDEX FROM b_zhuiju_us.typecho_relationships;
SHOW INDEX FROM b_zhuiju_us.typecho_fields;

SELECT TABLE_NAME, TABLE_ROWS, ROW_FORMAT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA='b_zhuiju_us'
  AND TABLE_NAME IN ('typecho_contents','typecho_metas','typecho_relationships','typecho_fields');

-- 数据分布：决定索引列序的依据
SELECT type, COUNT(*) FROM b_zhuiju_us.typecho_contents GROUP BY type;
SELECT authorId, COUNT(*) FROM b_zhuiju_us.typecho_contents GROUP BY authorId;
SELECT type, COUNT(*) FROM b_zhuiju_us.typecho_metas GROUP BY type;


-- ── 第 1 步：优化前 EXPLAIN（留底用于对比）────────────────────────────────
-- 把 ? 换成第 0 步查出的真实值。type='post_draft'、authorId=1 是最常见情况。
EXPLAIN SELECT * FROM b_zhuiju_us.typecho_contents
 WHERE type='post_draft' AND (parent=0 OR parent IS NULL) AND authorId=1
 ORDER BY created DESC;

EXPLAIN SELECT * FROM b_zhuiju_us.typecho_metas WHERE type='tag' AND name='古装' LIMIT 1;
EXPLAIN SELECT mid FROM b_zhuiju_us.typecho_metas WHERE type='category' AND name='剧集';


-- ── 第 2 步：创建索引 ──────────────────────────────────────────────────────

-- [索引 1] typecho_contents
-- 目标 SQL：WHERE type=? AND (parent=? OR parent IS NULL) AND authorId=? ORDER BY created DESC
-- 现状：原生 schema 只有 PRIMARY(cid) / UNIQUE(slug) / KEY(created)，该谓词无索引可用，
--       每次 newPost 全表扫描约 14600 行，且 SELECT * 会把 longtext 正文一并读出。
-- 列序理由：
--   - type 打头：目标查询 rows_sent=0，说明命中的 type 分桶几乎为空（post_draft），
--     选择性最高，索引第一列就能把范围切到 0 行。
--   - authorId 次之：单作者站选择性≈1，放首位等于没过滤（ChatGPT 建议的
--     (authorId, type, ...) 列序在此数据分布下是错的）。
--   - parent 第三：因为是 OR ... IS NULL，只能做索引条件下推，不能限定范围。
--   - created 末尾：满足 ORDER BY，避免 filesort。
ALTER TABLE b_zhuiju_us.typecho_contents
  ADD INDEX idx_tg2blog_type_author (type, authorId, parent, created);

-- [索引 2] typecho_metas
-- 目标 SQL：WHERE type=? AND name=? （分类/标签按名字解析成 mid）
-- 现状：原生 schema 只有 PRIMARY(mid) / KEY(slug)，每篇文章的每个标签查一次，
--       580 篇文章产生 2127 次全表扫描、共 506 万行。
-- 用 name(64) 前缀：name 是 varchar(200)，utf8mb4 下整列入索引 = 800 字节，
--       在 COMPACT 行格式（767 字节上限）的老库上会直接报错。64 字符对标签名
--       已经足够选择性，且在任何行格式下都安全。
ALTER TABLE b_zhuiju_us.typecho_metas
  ADD INDEX idx_tg2blog_type_name (type, name(64));

-- [索引 3] typecho_relationships（可选，但建议一起做）
-- 目标：Typecho 发布后会 UPDATE typecho_metas SET count=(SELECT COUNT(*) ...
--       FROM typecho_relationships WHERE mid=?)，本次统计里执行了 2707 次。
-- 现状：原生 PRIMARY KEY 是 (cid, mid)，WHERE mid=? 用不上主键前缀 → 索引全扫。
-- 先确认不存在同名/等价索引再建。
ALTER TABLE b_zhuiju_us.typecho_relationships
  ADD INDEX idx_tg2blog_mid (mid);

-- [typecho_fields] 不需要新增索引。
-- 目标 SQL：SELECT cid FROM typecho_fields WHERE cid=? AND name=?
-- 原生 PRIMARY KEY(cid, name) 已完全覆盖，走 const/eq_ref，无需处理。


-- ── 第 3 步：优化后 EXPLAIN（与第 1 步对比）──────────────────────────────
-- 期望：type 从 ALL → ref/range，key 显示上面的索引名，rows 从万级降到个位数，
--       Extra 不再出现 "Using filesort"（contents 那条）。
EXPLAIN SELECT * FROM b_zhuiju_us.typecho_contents
 WHERE type='post_draft' AND (parent=0 OR parent IS NULL) AND authorId=1
 ORDER BY created DESC;

EXPLAIN SELECT * FROM b_zhuiju_us.typecho_metas WHERE type='tag' AND name='古装' LIMIT 1;
EXPLAIN SELECT mid FROM b_zhuiju_us.typecho_metas WHERE type='category' AND name='剧集';


-- ── 第 4 步：回滚（只删本次新增的索引，不动 Typecho 原生索引）─────────────
-- ALTER TABLE b_zhuiju_us.typecho_contents      DROP INDEX idx_tg2blog_type_author;
-- ALTER TABLE b_zhuiju_us.typecho_metas         DROP INDEX idx_tg2blog_type_name;
-- ALTER TABLE b_zhuiju_us.typecho_relationships DROP INDEX idx_tg2blog_mid;


-- ── 第 5 步：效果复核 ──────────────────────────────────────────────────────
-- 先清空历史统计，跑一段时间自动发文后再看
-- TRUNCATE TABLE performance_schema.events_statements_summary_by_digest;

SELECT COUNT_STAR,
       ROUND(SUM_TIMER_WAIT/1000000000000,2) AS total_sec,
       ROUND(AVG_TIMER_WAIT/1000000000,3)    AS avg_ms,
       SUM_ROWS_EXAMINED, SUM_ROWS_SENT, SUM_NO_INDEX_USED,
       LEFT(DIGEST_TEXT,120) AS sql_head
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME='b_zhuiju_us'
ORDER BY SUM_TIMER_WAIT DESC LIMIT 30;


-- ── 附：排查历史重复文章（验证 hash_key 漂移造成的重复建文）───────────────
-- tg2blog 的 slug 格式是 {拼音}-{年份}-4k，Typecho 遇到 slug 冲突会自动加后缀。
-- 下面这条把带数字后缀的 slug 归并，count>1 的就是同一部影片的重复文章。
-- 需要 MySQL 8.0（REGEXP_REPLACE）。
SELECT REGEXP_REPLACE(slug,'[-_][0-9]+$','') AS base_slug,
       COUNT(*) AS n,
       GROUP_CONCAT(cid ORDER BY created) AS cids,
       GROUP_CONCAT(slug ORDER BY created) AS slugs
FROM b_zhuiju_us.typecho_contents
WHERE type='post'
GROUP BY base_slug
HAVING n > 1
ORDER BY n DESC
LIMIT 50;
