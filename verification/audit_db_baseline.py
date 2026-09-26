import sqlite3
import hashlib

con = sqlite3.connect('d:/DeepVision/instance/deepvision.db')
cur = con.cursor()
cur.execute('PRAGMA integrity_check')
integ = cur.fetchall()[0][0]
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = cur.fetchall()
table_count = len(tables)
sig = hashlib.sha256(''.join(t[1] or '' for t in tables).encode()).hexdigest()[:16]

counts = {}
for tbl in [t[0] for t in tables]:
    try:
        cur.execute(f"SELECT COUNT(*) FROM [{tbl}]")
        counts[tbl] = cur.fetchone()[0]
    except Exception as e:
        counts[tbl] = str(e)

print(f"DB_INTEGRITY: {integ}")
print(f"TABLES_COUNT: {table_count}")
print(f"SCHEMA_SIGNATURE: {sig}")
for k, v in counts.items():
    print(f"  {k}: {v}")
con.close()
