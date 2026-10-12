import os
import hashlib
import shutil
import sqlite3
from pathlib import Path

ROOT_DIR = Path("D:/DeepVision")
db_path = ROOT_DIR / "instance" / "deepvision.db"
backup_dir = ROOT_DIR / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)
backup_path = backup_dir / "deepvision_sqlite_baseline_20261010.db"

# 1. Check integrity
conn = sqlite3.connect(str(db_path))
c = conn.cursor()
c.execute("PRAGMA integrity_check;")
status = c.fetchone()[0]

c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in c.fetchall()]

row_counts = {}
for t in tables:
    c.execute(f"SELECT COUNT(*) FROM `{t}`;")
    row_counts[t] = c.fetchone()[0]

conn.close()

# 2. Hash source
with open(db_path, "rb") as f:
    source_sha256 = hashlib.sha256(f.read()).hexdigest()

# 3. Create backup copy
shutil.copy2(str(db_path), str(backup_path))

# 4. Hash backup
with open(backup_path, "rb") as f:
    backup_sha256 = hashlib.sha256(f.read()).hexdigest()

print("=" * 60)
print("DEEPVISION SQLITE BACKUP AND INTEGRITY AUDIT")
print("=" * 60)
print(f"Source DB Path:    {db_path}")
print(f"Source DB Size:    {db_path.stat().st_size} bytes")
print(f"Source SHA256:     {source_sha256}")
print(f"Backup Path:       {backup_path}")
print(f"Backup SHA256:     {backup_sha256}")
print(f"Integrity Check:   {status}")
print(f"Total Tables:      {len(tables)}")
print(f"Match Confirmed:   {source_sha256 == backup_sha256}")
print("\nTable Row Counts:")
for t, cnt in sorted(row_counts.items()):
    print(f"  {t:<25}: {cnt:>6} rows")
