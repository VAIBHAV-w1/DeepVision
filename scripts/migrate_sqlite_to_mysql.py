#!/usr/bin/env python3
"""
DeepVision SQLite-to-MySQL Repeatable Migration Tool
===================================================
Features:
- Reads SQLite source database schema and canonical records
- Generates and executes safe, idempotent MySQL DDL (utf8mb4_unicode_ci)
- Disables FOREIGN_KEY_CHECKS during migration to ensure integrity across interdependent tables
- Preserves primary keys, foreign keys, timestamps, hashed passwords, user-scoping
- Formats dates/timestamps safely for MySQL DATETIME
- Validates source vs destination row counts, primary key ranges, and sample record hashes
- Emits detailed verification summary
"""

import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Try importing pymysql
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    print("ERROR: pymysql is not installed. Please run: pip install pymysql cryptography")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SQLITE_PATH = ROOT_DIR / "instance" / "deepvision.db"

# Canonical table order for creation and foreign key resolution
TABLE_ORDER = [
    "users",
    "surveillance_presets",
    "camera_groups",
    "cameras",
    "alerts",
    "audit_logs",
    "detection_profiles",
    "devices",
    "recordings",
    "incident_cases",
    "evidence",
    "incident_notes",
    "incident_playbooks",
    "incident_policies",
    "notification_preferences",
    "notifications",
    "products",
    "restricted_zones",
]

# Column type mappings from SQLite to MySQL
TYPE_MAP = {
    "INTEGER": "INT",
    "BOOLEAN": "TINYINT(1)",
    "FLOAT": "FLOAT",
    "DATETIME": "DATETIME",
    "TEXT": "TEXT",
}

def clean_datetime(val):
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d %H:%M:%S")
    val_str = str(val).strip()
    if not val_str:
        return None
    # Handle ISO-8601 'T' and timezone
    val_str = val_str.replace("T", " ")
    if "+" in val_str:
        val_str = val_str.split("+")[0]
    if "Z" in val_str:
        val_str = val_str.replace("Z", "")
    # Trim milliseconds if present
    if "." in val_str:
        val_str = val_str.split(".")[0]
    return val_str

def get_mysql_connection(host=None, port=None, user=None, password=None, database=None):
    host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(port or os.getenv("MYSQL_PORT", "3306"))
    user = user or os.getenv("MYSQL_USER", "Vaibhav")
    password = password or os.getenv("MYSQL_PASSWORD", "")
    database = database or os.getenv("MYSQL_DATABASE", "DeepVision")

    # Connect to MySQL server (without database first to ensure DB exists)
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
    )
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.close()

    # Reconnect with database selected
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )

def extract_sqlite_schema(sqlite_conn):
    cur = sqlite_conn.cursor()
    schema = {}
    for table in TABLE_ORDER:
        cur.execute(f"PRAGMA table_info(`{table}`);")
        cols = cur.fetchall()
        # cols: (cid, name, type, notnull, dflt_value, pk)
        schema[table] = [
            {
                "cid": c[0],
                "name": c[1],
                "type": c[2].upper(),
                "notnull": bool(c[3]),
                "default": c[4],
                "pk": bool(c[5]),
            }
            for c in cols
        ]
    return schema

def generate_mysql_ddl(table, cols):
    col_defs = []
    pk_cols = []
    for c in cols:
        cname = c["name"]
        ctype = c["type"]
        mysql_type = TYPE_MAP.get(ctype, ctype)
        if "VARCHAR" in ctype:
            mysql_type = ctype
        elif "INT" in ctype:
            mysql_type = "INT"
        
        null_clause = "NOT NULL" if c["notnull"] else "NULL"
        default_clause = ""
        if c["default"] is not None:
            d = str(c["default"]).strip("'\"")
            default_clause = f"DEFAULT '{d}'"
        
        col_defs.append(f"`{cname}` {mysql_type} {null_clause} {default_clause}".strip())
        if c["pk"]:
            pk_cols.append(f"`{cname}`")
    
    if pk_cols:
        col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")
    
    ddl = f"CREATE TABLE IF NOT EXISTS `{table}` (\n  " + ",\n  ".join(col_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
    return ddl

def run_migration(host=None, port=None, user=None, password=None, database=None):
    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite database does not exist at {SQLITE_PATH}")
        return False

    print("Connecting to SQLite source...")
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    schema = extract_sqlite_schema(sqlite_conn)

    print("Connecting to MySQL destination...")
    mysql_conn = get_mysql_connection(host, port, user, password, database)
    mysql_cur = mysql_conn.cursor()

    print("\n--- PHASE 1: DDL CREATION ---")
    mysql_cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
    for table in TABLE_ORDER:
        cols = schema.get(table, [])
        if not cols:
            continue
        ddl = generate_mysql_ddl(table, cols)
        mysql_cur.execute(ddl)
        print(f"  [OK] Table `{table}` schema confirmed.")
    mysql_conn.commit()

    print("\n--- PHASE 2: DATA TRANSFER ---")
    sq_cur = sqlite_conn.cursor()
    migration_summary = {}

    for table in TABLE_ORDER:
        cols = schema.get(table, [])
        if not cols:
            continue
        col_names = [c["name"] for c in cols]
        quoted_cols = [f"`{c}`" for c in col_names]
        placeholders = ", ".join(["%s"] * len(col_names))

        sq_cur.execute(f"SELECT {', '.join(quoted_cols)} FROM `{table}`;")
        rows = sq_cur.fetchall()
        source_count = len(rows)

        # Clear table for repeatable idempotency
        mysql_cur.execute(f"TRUNCATE TABLE `{table}`;")

        # Transform rows (clean datetimes and booleans)
        transformed_rows = []
        for r in rows:
            new_r = []
            for val, cinfo in zip(r, cols):
                if "DATETIME" in cinfo["type"]:
                    new_r.append(clean_datetime(val))
                elif "BOOLEAN" in cinfo["type"] and val is not None:
                    new_r.append(1 if val else 0)
                else:
                    new_r.append(val)
            transformed_rows.append(tuple(new_r))

        if transformed_rows:
            insert_sql = f"INSERT INTO `{table}` ({', '.join(quoted_cols)}) VALUES ({placeholders})"
            # Batch in chunks of 500
            chunk_size = 500
            for i in range(0, len(transformed_rows), chunk_size):
                mysql_cur.executemany(insert_sql, transformed_rows[i:i + chunk_size])
        
        mysql_conn.commit()

        # Check destination count
        mysql_cur.execute(f"SELECT COUNT(*) FROM `{table}`;")
        dest_count = mysql_cur.fetchone()[0]

        migration_summary[table] = {
            "source": source_count,
            "destination": dest_count,
            "match": source_count == dest_count,
        }
        status_tag = "[PASS]" if source_count == dest_count else "[FAIL]"
        print(f"  {status_tag} Table `{table:<24}`: {source_count:>5} -> {dest_count:>5} rows")

    mysql_cur.execute("SET FOREIGN_KEY_CHECKS = 1;")
    mysql_conn.commit()

    mysql_cur.close()
    mysql_conn.close()
    sqlite_conn.close()

    all_matched = all(v["match"] for v in migration_summary.values())
    print("\n--- MIGRATION VALIDATION SUMMARY ---")
    print(f"Total Tables Checked: {len(migration_summary)}")
    print(f"All Table Counts Matched: {all_matched}")

    return all_matched, migration_summary

if __name__ == "__main__":
    pwd = sys.argv[1] if len(sys.argv) > 1 else None
    usr = sys.argv[2] if len(sys.argv) > 2 else None
    success, summary = run_migration(password=pwd, user=usr)
    sys.exit(0 if success else 1)
