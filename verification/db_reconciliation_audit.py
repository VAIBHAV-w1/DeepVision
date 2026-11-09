"""
DeepVision Database Reconciliation Audit Script
Read-only inspection of instance/deepvision.db and schema files.
Does not mutate or delete any data.
"""
import sqlite3
import hashlib
from pathlib import Path

DB_PATH = Path("instance/deepvision.db")

def audit_database():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} does not exist!")
        return

    conn = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True)
    c = conn.cursor()

    # 1. Tables
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables = [r[0] for r in c.fetchall()]

    print("=" * 60)
    print(f"DEEPVISION SQLITE DATABASE AUDIT: {DB_PATH}")
    print("=" * 60)
    print(f"Total Tables: {len(tables)}")
    print("-" * 60)

    total_records = 0
    table_counts = {}
    for t in tables:
        c.execute(f'SELECT COUNT(*) FROM "{t}";')
        cnt = c.fetchone()[0]
        table_counts[t] = cnt
        total_records += cnt
        print(f"  {t:<28}: {cnt:>6} records")

    print("-" * 60)
    print(f"Total Historical Records: {total_records}")
    print("=" * 60)

    # 2. Schema Hash
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
    schema_sql = "".join(str(r[0]) for r in c.fetchall())
    sig = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()[:16]
    print(f"Schema Signature: {sig}")

    # 3. Secondary Indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    indexes = [r[0] for r in c.fetchall()]
    print(f"Secondary Indexes ({len(indexes)}):")
    for idx in indexes:
        print(f"  - {idx}")

    conn.close()

if __name__ == "__main__":
    audit_database()
