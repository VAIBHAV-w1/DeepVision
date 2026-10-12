import sqlite3
import os

p = 'D:/DeepVision/instance/deepvision.db'
print('DB Exists:', os.path.exists(p), 'Size (bytes):', os.path.getsize(p))
conn = sqlite3.connect(p)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]
print(f'Total tables: {len(tables)}')
for t in tables:
    c.execute(f"SELECT count(*) FROM {t}")
    cnt = c.fetchone()[0]
    print(f"  {t}: {cnt}")

print("\n--- User 2 vs User 14 counts ---")
for uid in [2, 14]:
    c.execute(f"SELECT id, email FROM users WHERE id = {uid}")
    u = c.fetchone()
    print(f"\nUser: {u}")
    if u:
        for t, col in [("alerts", "user_id"), ("evidence", "user_id"), ("cases", "user_id"), ("notifications", "user_id"), ("recordings", "user_id")]:
            try:
                c.execute(f"SELECT count(*) FROM {t} WHERE {col} = {uid}")
                print(f"  {t} (owned): {c.fetchone()[0]}")
            except Exception as e:
                print(f"  {t}: error {e}")

conn.close()
