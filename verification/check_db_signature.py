import sqlite3
import hashlib

conn = sqlite3.connect('instance/deepvision.db')
cursor = conn.cursor()
cursor.execute('PRAGMA integrity_check;')
print('Integrity:', cursor.fetchone()[0])

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [r[0] for r in cursor.fetchall()]
print(f'Tables count: {len(tables)}')

schema_sql = ''
for t in tables:
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{t}';")
    row = cursor.fetchone()
    if row and row[0]:
        schema_sql += row[0]

sig = hashlib.sha256(schema_sql.encode('utf-8')).hexdigest()[:16]
print('Schema Signature:', sig)
assert len(tables) == 18, f"Expected 18 tables, got {len(tables)}"
assert sig == 'cc2d13f77b681107', f"Expected signature cc2d13f77b681107, got {sig}"
print("DATABASE VERIFICATION PASSED PERFECTLY!")
