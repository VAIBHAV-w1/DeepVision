import sqlite3
import hashlib

conn = sqlite3.connect(r'd:/DeepVision/instance/deepvision.db')
c = conn.cursor()
c.execute('PRAGMA integrity_check;')
print('Integrity:', c.fetchone()[0])
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
tables = [r[0] for r in c.fetchall()]
print('Table count:', len(tables))
c.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
schema_sql = ''.join(str(r[0]) for r in c.fetchall())
sig = hashlib.sha256(schema_sql.encode('utf-8')).hexdigest()[:16]
print('Schema signature:', sig)
counts = {}
for t in tables:
    c.execute(f"SELECT COUNT(*) FROM {t}")
    counts[t] = c.fetchone()[0]
for k, v in sorted(counts.items()):
    print(f'  {k}: {v}')
conn.close()
