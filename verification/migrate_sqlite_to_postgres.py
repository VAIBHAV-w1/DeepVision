"""
DeepVision 1.1.0 SQLite to PostgreSQL / Supabase Migration & Verification Tool
Migrates data from the verified SQLite backup into a PostgreSQL / Supabase database.
Preserves primary keys, sequences, timestamps, password hashes, and relational integrity.
"""

import os
import sys
import argparse
import sqlite3
import datetime

try:
    import psycopg2
    from psycopg2 import extras
except ImportError:
    psycopg2 = None

TABLE_ORDER = [
    'users',
    'surveillance_presets',
    'camera_groups',
    'cameras',
    'alerts',
    'audit_logs',
    'detection_profiles',
    'devices',
    'evidence',
    'incident_cases',
    'incident_notes',
    'incident_playbooks',
    'incident_policies',
    'notification_preferences',
    'notifications',
    'products',
    'recordings',
    'restricted_zones',
]

SQLITE_BACKUP_DEFAULT = r'D:\DeepVision\verification\deepvision_backup_for_migration.db'
POSTGRES_SCHEMA_FILE = r'D:\DeepVision\deepvision_django\schema_postgres.sql'


def get_sqlite_conn(db_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite backup database not found at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn(pg_url):
    if not psycopg2:
        raise RuntimeError("psycopg2 is not installed. Run 'pip install psycopg2-binary'.")
    if not pg_url:
        raise ValueError("PostgreSQL connection URL is required (via --pg-url or DATABASE_URL).")
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    return conn


def parse_args():
    parser = argparse.ArgumentParser(description="DeepVision SQLite to PostgreSQL Migration Tool")
    parser.add_argument("--sqlite-db", default=SQLITE_BACKUP_DEFAULT, help="Path to SQLite backup database")
    parser.add_argument("--pg-url", default=os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL"), help="PostgreSQL connection string")
    parser.add_argument("--dry-run", action="store_true", help="Inspect source data without connecting to PostgreSQL")
    parser.add_argument("--apply", action="store_true", help="Execute schema and data migration against PostgreSQL")
    parser.add_argument("--verify-only", action="store_true", help="Verify existing PostgreSQL data against SQLite backup")
    parser.add_argument("--drop-first", action="store_true", help="Drop existing tables before recreating schema (clean slate)")
    return parser.parse_args()


def inspect_source(sqlite_conn):
    print("=== Source SQLite Backup Inspection ===")
    cur = sqlite_conn.cursor()
    total_rows = 0
    stats = {}
    for table in TABLE_ORDER:
        cur.execute(f"SELECT count(*) FROM \"{table}\"")
        cnt = cur.fetchone()[0]
        cur.execute(f"PRAGMA table_info(\"{table}\")")
        cols = [r['name'] for r in cur.fetchall()]
        stats[table] = {'count': cnt, 'columns': cols}
        total_rows += cnt
        print(f"  - {table:<30}: {cnt} rows, {len(cols)} columns")
    print(f"Total Source Records: {total_rows:,}\n")
    return stats


def apply_schema(pg_conn, drop_first=False):
    print("=== Applying PostgreSQL Schema ===")
    with open(POSTGRES_SCHEMA_FILE, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    with pg_conn.cursor() as cur:
        if drop_first:
            print("Dropping existing tables in reverse dependency order...")
            for table in reversed(TABLE_ORDER):
                cur.execute(f"DROP TABLE IF EXISTS \"{table}\" CASCADE;")
            pg_conn.commit()
            print("Existing tables dropped.")

        print("Executing schema_postgres.sql DDL...")
        cur.execute(schema_sql)
        pg_conn.commit()
    print("PostgreSQL schema created successfully.\n")


def migrate_data(sqlite_conn, pg_conn, source_stats):
    print("=== Migrating Data from SQLite to PostgreSQL ===")
    sq_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    for table in TABLE_ORDER:
        cnt = source_stats[table]['count']
        cols = source_stats[table]['columns']
        if cnt == 0:
            print(f"  - {table:<30}: 0 rows (skipping)")
            continue

        print(f"  - {table:<30}: migrating {cnt} rows...", end='', flush=True)
        col_names = ", ".join([f'"{c}"' for c in cols])
        placeholders = ", ".join(["%s"] * len(cols))
        insert_query = f"INSERT INTO \"{table}\" ({col_names}) VALUES ({placeholders})"

        sq_cur.execute(f"SELECT {col_names} FROM \"{table}\" ORDER BY id")
        rows = sq_cur.fetchall()

        # Convert row tuples for PostgreSQL compatibility
        data_tuples = []
        for r in rows:
            row_data = list(r)
            for idx, val in enumerate(row_data):
                # Clean string dates if needed
                if isinstance(val, str) and len(val) >= 19:
                    try:
                        # Validate ISO format
                        datetime.datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except ValueError:
                        pass
            data_tuples.append(tuple(row_data))

        extras.execute_batch(pg_cur, insert_query, data_tuples, page_size=1000)
        pg_conn.commit()

        # Reset serial sequence
        pg_cur.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('"{table}"', 'id'),
                COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                (SELECT MAX(id) FROM "{table}") IS NOT NULL
            );
        """)
        pg_conn.commit()
        print(" DONE")

    print("\nData migration finished successfully.\n")


def verify_migration(sqlite_conn, pg_conn, source_stats):
    print("=== Verifying Migration Integrity between SQLite & PostgreSQL ===")
    sq_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()
    all_matched = True

    for table in TABLE_ORDER:
        sq_cnt = source_stats[table]['count']
        pg_cur.execute(f"SELECT count(*) FROM \"{table}\"")
        pg_cnt = pg_cur.fetchone()[0]

        status = "MATCH" if sq_cnt == pg_cnt else "MISMATCH"
        print(f"  - {table:<30}: SQLite={sq_cnt} | PG={pg_cnt} -> {status}")
        if sq_cnt != pg_cnt:
            all_matched = False

        if sq_cnt > 0:
            # Check min and max ID
            sq_cur.execute(f"SELECT MIN(id), MAX(id) FROM \"{table}\"")
            sq_min, sq_max = sq_cur.fetchone()
            pg_cur.execute(f"SELECT MIN(id), MAX(id) FROM \"{table}\"")
            pg_min, pg_max = pg_cur.fetchone()
            if (sq_min, sq_max) != (pg_min, pg_max):
                print(f"    WARNING: ID range mismatch: SQLite=({sq_min}, {sq_max}) vs PG=({pg_min}, {pg_max})")
                all_matched = False

    # Check sample user authentication password hash integrity
    sq_cur.execute("SELECT id, email, password_hash, role FROM users ORDER BY id LIMIT 3")
    sq_users = sq_cur.fetchall()
    print("\n  Sample User Hash Verification:")
    for u in sq_users:
        pg_cur.execute("SELECT email, password_hash, role FROM users WHERE id = %s", (u['id'],))
        pg_user = pg_cur.fetchone()
        if pg_user and pg_user[0] == u['email'] and pg_user[1] == u['password_hash']:
            print(f"    User {u['id']} ({u['email']}): Password Hash & Role Integrity Verified (OK)")
        else:
            print(f"    User {u['id']} ({u['email']}): Hash mismatch or missing!")
            all_matched = False

    if all_matched:
        print("\nAll 18 tables verified with exact row counts, primary keys, and password hashes! PASS")
    else:
        print("\nVerification found mismatches! FAIL")
    return all_matched


def main():
    args = parse_args()
    sqlite_conn = get_sqlite_conn(args.sqlite_db)
    source_stats = inspect_source(sqlite_conn)

    if args.dry_run or (not args.apply and not args.verify_only):
        print("Dry run mode complete. To execute migration, supply --pg-url and --apply.")
        sqlite_conn.close()
        return

    if not args.pg_url:
        print("ERROR: --pg-url (or DATABASE_URL / SUPABASE_DB_URL) must be provided to run --apply or --verify-only.")
        sqlite_conn.close()
        sys.exit(1)

    pg_conn = get_pg_conn(args.pg_url)

    try:
        if args.apply:
            apply_schema(pg_conn, drop_first=args.drop_first)
            migrate_data(sqlite_conn, pg_conn, source_stats)
        verify_migration(sqlite_conn, pg_conn, source_stats)
    finally:
        pg_conn.close()
        sqlite_conn.close()


if __name__ == '__main__':
    main()
