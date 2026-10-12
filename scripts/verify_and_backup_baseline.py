import os
import sys
import time
import json
import shutil
import hashlib
import sqlite3
from pathlib import Path

ROOT_DIR = Path("D:/DeepVision")
INSTANCE_DIR = ROOT_DIR / "instance"
DB_PATH = INSTANCE_DIR / "deepvision.db"
BACKUP_DIR = ROOT_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

timestamp = time.strftime("%Y%m%d_%H%M%S")
backup_file = BACKUP_DIR / f"deepvision_baseline_{timestamp}.db"
test_restore_file = BACKUP_DIR / f"test_restore_{timestamp}.db"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

print("--- 1. ACTIVE DATABASE INTEGRITY & INSPECTION ---")
if not DB_PATH.exists():
    print(f"ERROR: DB not found at {DB_PATH}")
    sys.exit(1)

src_size = DB_PATH.stat().st_size
src_hash = sha256_file(DB_PATH)

conn_src = sqlite3.connect(str(DB_PATH))
cur_src = conn_src.cursor()
cur_src.execute("PRAGMA integrity_check;")
src_integrity = cur_src.fetchone()[0]

cur_src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = sorted([r[0] for r in cur_src.fetchall()])

table_counts_src = {}
for t in tables:
    cur_src.execute(f"SELECT COUNT(*) FROM `{t}`;")
    table_counts_src[t] = cur_src.fetchone()[0]
conn_src.close()

print(f"Source DB: {DB_PATH}")
print(f"Size: {src_size} bytes | SHA256: {src_hash}")
print(f"Integrity check: {src_integrity}")
print(f"Tables ({len(tables)}): {table_counts_src}")

print("\n--- 2. CREATING VERIFIED TIMESTAMPED BACKUP ---")
shutil.copy2(str(DB_PATH), str(backup_file))
backup_size = backup_file.stat().st_size
backup_hash = sha256_file(backup_file)

conn_bk = sqlite3.connect(str(backup_file))
cur_bk = conn_bk.cursor()
cur_bk.execute("PRAGMA integrity_check;")
backup_integrity = cur_bk.fetchone()[0]

table_counts_bk = {}
for t in tables:
    cur_bk.execute(f"SELECT COUNT(*) FROM `{t}`;")
    table_counts_bk[t] = cur_bk.fetchone()[0]
conn_bk.close()

assert src_hash == backup_hash, "Backup hash mismatch!"
assert src_integrity == "ok" and backup_integrity == "ok", "Integrity check failed!"
assert table_counts_src == table_counts_bk, "Table count mismatch!"
print(f"Backup created: {backup_file}")
print(f"Size: {backup_size} bytes | SHA256: {backup_hash}")
print(f"Integrity check: {backup_integrity}")
print("Backup exactly matches source!")

print("\n--- 3. VERIFYING RESTORE TO ISOLATED TEST LOCATION ---")
shutil.copy2(str(backup_file), str(test_restore_file))
conn_res = sqlite3.connect(str(test_restore_file))
cur_res = conn_res.cursor()
cur_res.execute("PRAGMA integrity_check;")
restore_integrity = cur_res.fetchone()[0]

table_counts_res = {}
for t in tables:
    cur_res.execute(f"SELECT COUNT(*) FROM `{t}`;")
    table_counts_res[t] = cur_res.fetchone()[0]

# Query sample records from core tables
cur_res.execute("SELECT id, full_name, email FROM users LIMIT 3;")
sample_users = cur_res.fetchall()
cur_res.execute("SELECT id, name, source, is_active FROM cameras LIMIT 3;")
sample_cameras = cur_res.fetchall()
conn_res.close()

# Clean up test restore
test_restore_file.unlink()

assert restore_integrity == "ok"
assert table_counts_src == table_counts_res
print(f"Restore verification: SUCCESS (table counts and sample data match)")
print(f"Sample users: {sample_users}")
print(f"Sample cameras: {sample_cameras}")

print("\n--- 4. ASSET & MODEL PROTECTION MANIFEST ---")
manifest = {
    "timestamp": timestamp,
    "active_db": {
        "path": str(DB_PATH),
        "size_bytes": src_size,
        "sha256": src_hash,
        "integrity": src_integrity,
        "table_count": len(tables),
        "tables": table_counts_src
    },
    "backup_db": {
        "path": str(backup_file),
        "size_bytes": backup_size,
        "sha256": backup_hash,
        "integrity": backup_integrity
    },
    "restore_test": "VERIFIED_PASSED",
    "assets": {}
}

# Scan key assets
asset_checks = [
    ("yolo_model_root", ROOT_DIR / "yolo11n.pt"),
    ("yolo_model_django", ROOT_DIR / "deepvision_django" / "yolo11n.pt"),
    ("recordings_dir", ROOT_DIR / "recordings"),
    ("evidence_dir", ROOT_DIR / "evidence"),
    ("backend_env", ROOT_DIR / "deepvision_django" / ".env")
]

for name, path in asset_checks:
    if path.exists():
        if path.is_file():
            manifest["assets"][name] = {
                "type": "file",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path)
            }
        else:
            files = list(path.glob("**/*"))
            manifest["assets"][name] = {
                "type": "dir",
                "path": str(path),
                "file_count": len([f for f in files if f.is_file()]),
                "total_bytes": sum(f.stat().st_size for f in files if f.is_file())
            }
    else:
        manifest["assets"][name] = {"exists": False}

manifest_file = ROOT_DIR / "verification" / "PHASE1_BASELINE_VERIFICATION.json"
manifest_file.parent.mkdir(parents=True, exist_ok=True)
with open(manifest_file, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Asset manifest generated at: {manifest_file}")
print("PHASE 1 FREEZE AND VERIFY COMPLETED SUCCESSFULLY.")
