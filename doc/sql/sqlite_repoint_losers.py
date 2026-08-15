#!/usr/bin/env python3
"""
把 content_posts 中「败者」行的 typecho_cid 改指向同组胜者。

配合 doc/sql/typecho_dedup_cleanup.sql 的阶段 2 使用。背景见该文件抬头。

要点：
  * 只 UPDATE，不 DELETE。typecho_cid 没有 UNIQUE 约束，多行共享同一个 cid 是
    合法状态，因此「改指向」不丢任何行。
  * 改动前把 (hash_key, 原 typecho_cid, 原 content_hash) 存进 tg2blog_dedup_backup。
  * 同时把 content_hash 置空，强制下一条消息真正推一次更新到胜者文章 —— 否则
    败者 key 会在 worker 第 7 步因指纹未变而短路，胜者文章拿不到最新内容。
  * UPDATE 带 `AND typecho_cid = 原值` 守卫，值已被改过就跳过并计入 skipped，
    重复执行安全。

用法（在 VM116739 宿主机执行，先 docker compose stop tg2blog）：
    python3 doc/sql/sqlite_repoint_losers.py --tsv /tmp/loser_map.tsv --dry-run
    python3 doc/sql/sqlite_repoint_losers.py --tsv /tmp/loser_map.tsv --apply
    python3 doc/sql/sqlite_repoint_losers.py --rollback
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone

DEFAULT_DB = "/home/tg2blog/data/db/tg2blog.sqlite"

BACKUP_DDL = """
CREATE TABLE IF NOT EXISTS tg2blog_dedup_backup (
    hash_key         TEXT    NOT NULL PRIMARY KEY,
    old_cid          INTEGER NOT NULL,
    new_cid          INTEGER NOT NULL,
    old_content_hash TEXT,
    backed_at        TEXT    NOT NULL
)
"""


def load_tsv(path: str) -> list[tuple[str, int, int]]:
    """读 mysql -B 导出的 TSV，返回 [(hash_key, loser_cid, winner_cid), ...]"""
    rows = []
    with open(path, encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        if header[:3] != ["loser_cid", "winner_cid", "hash_key"]:
            sys.exit(f"表头不对，期望 loser_cid/winner_cid/hash_key，实际 {header}")
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            loser, winner, hash_key = line.split("\t", 2)
            rows.append((hash_key, int(loser), int(winner)))
    return rows


def repoint(conn: sqlite3.Connection, rows: list, apply: bool) -> None:
    conn.execute(BACKUP_DDL)
    now = datetime.now(timezone.utc).isoformat()
    updated = skipped = missing = 0

    for hash_key, loser, winner in rows:
        cur = conn.execute(
            "SELECT typecho_cid, content_hash FROM content_posts WHERE hash_key=?",
            (hash_key,),
        ).fetchone()
        if cur is None:
            print(f"  ⚠️  hash_key 不存在: {hash_key}")
            missing += 1
            continue
        if cur[0] != loser:
            print(f"  ⏭️  已改过或不匹配: {hash_key} 当前cid={cur[0]} 期望={loser}")
            skipped += 1
            continue
        if apply:
            conn.execute(
                "INSERT OR IGNORE INTO tg2blog_dedup_backup "
                "(hash_key, old_cid, new_cid, old_content_hash, backed_at) "
                "VALUES (?,?,?,?,?)",
                (hash_key, loser, winner, cur[1], now),
            )
            conn.execute(
                "UPDATE content_posts SET typecho_cid=?, content_hash=NULL, updated_at=? "
                "WHERE hash_key=? AND typecho_cid=?",
                (winner, now, hash_key, loser),
            )
        updated += 1

    if apply:
        conn.commit()
    print(f"\n{'已改指向' if apply else '将改指向'}: {updated}  "
          f"跳过: {skipped}  hash_key缺失: {missing}")
    if not apply:
        print("（--dry-run，未写入任何数据）")


def rollback(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT hash_key, old_cid, new_cid, old_content_hash FROM tg2blog_dedup_backup"
    ).fetchall()
    if not rows:
        sys.exit("备份表为空，无可回滚内容")
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for hash_key, old_cid, new_cid, old_hash in rows:
        cur = conn.execute(
            "UPDATE content_posts SET typecho_cid=?, content_hash=?, updated_at=? "
            "WHERE hash_key=? AND typecho_cid=?",
            (old_cid, old_hash, now, hash_key, new_cid),
        )
        n += cur.rowcount
    conn.commit()
    print(f"已回滚 {n}/{len(rows)} 行")
    if n < len(rows):
        print("（未回滚的行说明 typecho_cid 已被后续运行改动，需人工确认）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--tsv")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    if args.rollback:
        rollback(conn)
        return
    if not args.tsv:
        sys.exit("需要 --tsv")
    if args.apply == args.dry_run:
        sys.exit("--apply 与 --dry-run 二选一")

    rows = load_tsv(args.tsv)
    print(f"读入映射 {len(rows)} 条\n")
    repoint(conn, rows, apply=args.apply)


if __name__ == "__main__":
    main()
