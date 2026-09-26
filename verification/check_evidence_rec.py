import os
import sys
import sqlite3
from pathlib import Path

ROOT = Path("d:/DeepVision")
DB_PATH = ROOT / "instance" / "deepvision.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT count(*) FROM recordings WHERE file_path LIKE 'evidence%'")
count_ev = c.fetchone()[0]
print(f"Recordings in DB with path starting with 'evidence': {count_ev}")

c.execute("SELECT id, filename, file_path, file_size FROM recordings WHERE file_path LIKE 'evidence%' ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    print(r)

c.execute("SELECT count(*) FROM recordings WHERE file_path NOT LIKE 'evidence%' AND (file_size > 0)")
print("Recordings in DB with non-evidence path and size > 0:", c.fetchone()[0])
