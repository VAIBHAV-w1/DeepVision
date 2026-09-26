import os
import sys
import sqlite3
import hashlib
from pathlib import Path

ROOT = Path("d:/DeepVision")
DB_PATH = ROOT / "instance" / "deepvision.db"

def inspect_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall() if not r[0].startswith("sqlite_")]
    print(f"Total tables: {len(tables)}")
    schema_str = "".join(c.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}'").fetchone()[0] for t in tables)
    sig = hashlib.sha256(schema_str.encode()).hexdigest()[:16]
    print(f"Schema signature: {sig}")

    print("\n--- CAMERAS ---")
    c.execute("SELECT * FROM cameras")
    cols = [d[0] for d in c.description]
    for r in c.fetchall():
        print(dict(zip(cols, r)))

    print("\n--- RECORDINGS COUNT & SAMPLE ---")
    c.execute("SELECT count(*) FROM recordings")
    print("Total recordings in DB:", c.fetchone()[0])
    c.execute("SELECT * FROM recordings ORDER BY id DESC LIMIT 10")
    cols = [d[0] for d in c.description]
    for r in c.fetchall():
        print(dict(zip(cols, r)))

    print("\n--- PHYSICAL RECORDINGS DIRECTORY ---")
    rec_dirs = [ROOT / "media" / "recordings", ROOT / "recordings", ROOT / "deepvision_django" / "media" / "recordings"]
    for rd in rec_dirs:
        if rd.exists():
            files = list(rd.glob("*.*"))
            print(f"Dir {rd} exists with {len(files)} files:")
            for f in files[:15]:
                print(f"  {f.name} ({f.stat().st_size} bytes)")
        else:
            print(f"Dir {rd} does not exist.")

if __name__ == "__main__":
    inspect_db()
