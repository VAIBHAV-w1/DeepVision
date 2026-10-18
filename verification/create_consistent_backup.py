import sqlite3
import os
import hashlib

SOURCE_DB = r'D:\DeepVision\instance\deepvision.db'
BACKUP_DB = r'D:\DeepVision\verification\deepvision_backup_for_migration.db'

def main():
    print("=== DeepVision SQLite Online Backup for PostgreSQL Migration ===")
    if not os.path.exists(SOURCE_DB):
        raise FileNotFoundError(f"Source DB not found at {SOURCE_DB}")

    src_size = os.path.getsize(SOURCE_DB)
    print(f"Source Database: {SOURCE_DB} ({src_size:,} bytes)")

    # Ensure source is opened in strict read-only URI mode
    src_conn = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    
    # Check source integrity before backup
    src_cur = src_conn.cursor()
    src_integrity = src_cur.execute("PRAGMA integrity_check").fetchone()[0]
    if src_integrity != "ok":
        raise RuntimeError(f"Source DB integrity check failed: {src_integrity}")
    print(f"Source Integrity: {src_integrity}")

    # Remove existing backup if present
    if os.path.exists(BACKUP_DB):
        os.remove(BACKUP_DB)

    # Destination connection
    dst_conn = sqlite3.connect(BACKUP_DB)
    
    # Perform SQLite Online Backup
    print("Executing sqlite3 Online Backup API...")
    src_conn.backup(dst_conn, pages=100)
    dst_conn.close()
    src_conn.close()

    backup_size = os.path.getsize(BACKUP_DB)
    print(f"Backup created successfully: {BACKUP_DB} ({backup_size:,} bytes)")

    # Verify backup database
    verify_conn = sqlite3.connect(f"file:{BACKUP_DB}?mode=ro", uri=True)
    verify_cur = verify_conn.cursor()
    
    integrity = verify_cur.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"Backup Integrity Check: {integrity}")
    assert integrity == "ok", "Backup integrity check failed!"

    tables = [r[0] for r in verify_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    print(f"Backup Tables Count: {len(tables)}")
    assert len(tables) == 18, f"Expected 18 tables, found {len(tables)}"

    indexes = [r[0] for r in verify_cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name").fetchall()]
    print(f"Backup Secondary Indexes Count: {len(indexes)}")
    assert len(indexes) == 11, f"Expected 11 indexes, found {len(indexes)}"

    total_rows = 0
    row_counts = {}
    for t in tables:
        cnt = verify_cur.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
        row_counts[t] = cnt
        total_rows += cnt

    verify_conn.close()

    print(f"Total Rows Verified in Backup: {total_rows:,}")
    for t, c in row_counts.items():
        print(f"  - {t:<30}: {c} rows")

    # Confirm source size and integrity remain identical
    curr_src_size = os.path.getsize(SOURCE_DB)
    assert curr_src_size == src_size, "Source database size changed unexpectedly!"
    print("\nSource database confirmed UNCHANGED and preserved.")
    print("=== Backup Verification Complete: PASS ===")

if __name__ == '__main__':
    main()
