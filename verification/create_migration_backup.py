import sqlite3
import os

src_path = os.path.abspath('instance/deepvision.db')
dst_path = os.path.abspath('verification/deepvision_backup_for_migration.db')

# Ensure destination directory exists
os.makedirs(os.path.dirname(dst_path), exist_ok=True)

# Connect to production database in STRICT read-only mode using URI
src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
dst = sqlite3.connect(dst_path)

with dst:
    src.backup(dst)

dst.close()
src.close()

# Verify the backup copy
check = sqlite3.connect(f"file:{dst_path}?mode=ro", uri=True)
cur = check.cursor()
integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()]
row_count = sum(cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables)
check.close()

print(f"SUCCESS: Created {os.path.getsize(dst_path)} bytes backup copy at {dst_path}")
print(f"Integrity: {integrity}")
print(f"Tables ({len(tables)}): {tables}")
print(f"Total Rows: {row_count}")
