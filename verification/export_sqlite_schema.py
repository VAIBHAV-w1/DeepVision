import sqlite3
import os

db_path = r'D:\DeepVision\instance\deepvision.db'
conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
cur = conn.cursor()

# Get tables
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
tables = cur.fetchall()

# Get indexes
cur.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY tbl_name, name")
indexes = cur.fetchall()

conn.close()

output_path = r'D:\DeepVision\verification\sqlite_schema_dump.sql'
with open(output_path, 'w', encoding='utf-8') as f:
    f.write("-- SQLite Schema Dump from instance/deepvision.db (Read-Only Inspection)\n\n")
    for name, sql in tables:
        f.write(f"-- Table: {name}\n")
        f.write(f"{sql};\n\n")
    f.write("-- Indexes\n\n")
    for name, tbl_name, sql in indexes:
        f.write(f"-- Index: {name} on {tbl_name}\n")
        f.write(f"{sql};\n\n")

print(f"Dumped {len(tables)} tables and {len(indexes)} indexes to {output_path}")
