"""
Verifies the SQLite baseline backup integrity, checksum, and exact row counts.
"""
import sqlite3
import hashlib
from pathlib import Path

backup_path = Path("backups/deepvision_sqlite_baseline_20261010.db")

def verify():
    if not backup_path.exists():
        print("ERROR: Backup file does not exist!")
        return

    data = backup_path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    size = len(data)

    conn = sqlite3.connect(f"file:{backup_path.resolve()}?mode=ro", uri=True)
    c = conn.cursor()

    c.execute("PRAGMA integrity_check;")
    integrity = c.fetchone()[0]

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables = [r[0] for r in c.fetchall()]

    counts = {}
    total = 0
    for t in tables:
        c.execute(f'SELECT COUNT(*) FROM "{t}";')
        cnt = c.fetchone()[0]
        counts[t] = cnt
        total += cnt

    conn.close()

    print("=" * 60)
    print("BACKUP VERIFICATION: backups/deepvision_sqlite_baseline_20261010.db")
    print("=" * 60)
    print(f"File Size:   {size:,} bytes")
    print(f"SHA-256:     {sha256}")
    print(f"Integrity:   {integrity}")
    print(f"Tables:      {len(tables)}")
    print(f"Total Rows:  {total:,}")
    print("-" * 60)
    for t, cnt in counts.items():
        print(f"  {t:<28}: {cnt:>6}")
    print("=" * 60)

if __name__ == "__main__":
    verify()
