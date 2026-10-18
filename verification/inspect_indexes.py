import sqlite3

conn = sqlite3.connect("file:D:/DeepVision/instance/deepvision.db?mode=ro", uri=True)
c = conn.cursor()
c.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY name")
rows = c.fetchall()
print(f"Total index entries: {len(rows)}")
for name, tbl, sql in rows:
    print(f"{name} (on {tbl}): {sql}")
conn.close()
