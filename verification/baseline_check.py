import sqlite3
import hashlib
import os
import glob
import subprocess
import json
import urllib.request

def check_baseline():
    print("=" * 60)
    print("DEEPVISION 1.1.0 READ-ONLY BASELINE VERIFICATION")
    print("=" * 60)
    
    # 1. Database read-only checks
    db_path = os.path.abspath("instance/deepvision.db")
    print(f"Database path: {db_path}")
    print(f"Exists: {os.path.exists(db_path)}, Size: {os.path.getsize(db_path)} bytes")
    
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    print(f"-wal exists: {os.path.exists(wal_path)}")
    print(f"-shm exists: {os.path.exists(shm_path)}")
    
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()
    
    cur.execute("PRAGMA journal_mode;")
    journal_mode = cur.fetchone()[0]
    print(f"PRAGMA journal_mode: {journal_mode}")
    
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchone()[0]
    print(f"PRAGMA integrity_check: {integrity}")
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cur.fetchall() if row[0] != 'sqlite_sequence']
    print(f"Tables ({len(tables)}): {tables}")
    
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
    schema_sql = "".join(str(r[0]) for r in cur.fetchall())
    signature = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()[:16]
    print(f"Table Schema Signature: {signature} (expected: cc2d13f77b681107)")
    
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_autoindex%' ORDER BY name;")
    indexes = [row[0] for row in cur.fetchall()]
    print(f"Secondary Indexes ({len(indexes)}): {indexes}")
    
    row_counts = {}
    for t in tables:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        row_counts[t] = cur.fetchone()[0]
    print("Row counts per table:")
    for t, cnt in row_counts.items():
        print(f"  {t}: {cnt}")
    conn.close()
    
    # 2. Inspect backups and archives
    print("\n--- Archives & Backups Inspection ---")
    archives = glob.glob("*.tar") + glob.glob("DeepVision-*/*.tar")
    for a in archives:
        print(f"Archive: {a} ({os.path.getsize(a)} bytes)")
    
    backup_files = glob.glob("instance/*backup*") + glob.glob("instance/*.bak") + glob.glob("*.bak")
    for b in backup_files:
        print(f"Backup file: {b} ({os.path.getsize(b)} bytes)")
        
    # 3. Live container inspection via docker CLI
    print("\n--- Live Container Inspection ---")
    try:
        proc = subprocess.run(
            ["docker", "inspect", "deepvision-app"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(proc.stdout)[0]
        cid = data["Id"][:12]
        image_id = data["Image"][:19]
        image_tag = data["Config"]["Image"]
        status = data["State"]["Status"]
        health = data["State"].get("Health", {}).get("Status", "N/A")
        restart_policy = data["HostConfig"]["RestartPolicy"]
        port_bindings = data["HostConfig"]["PortBindings"]
        mounts = [(m["Source"], m["Destination"], m["Mode"]) for m in data.get("Mounts", [])]
        
        print(f"Container ID: {cid}")
        print(f"Image ID: {image_id}")
        print(f"Image Tag: {image_tag}")
        print(f"Status: {status} (Health: {health})")
        print(f"Restart Policy: {restart_policy}")
        print(f"Port Bindings: {port_bindings}")
        print(f"Mounts: {mounts}")
    except Exception as e:
        print(f"Docker inspect error: {e}")
        
    # 4. Live Health Endpoint Check
    print("\n--- Live Endpoint Check ---")
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8000/api/health/", timeout=5)
        body = req.read().decode("utf-8")
        print(f"HTTP Status: {req.status}")
        print(f"Response Body: {body}")
    except Exception as e:
        print(f"Endpoint check error: {e}")

if __name__ == "__main__":
    check_baseline()
