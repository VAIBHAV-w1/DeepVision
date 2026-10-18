"""
Safe target database inspector.
Tests connection to PostgreSQL and inspects existing public tables.
Never leaks credentials.
"""
import os
import sys

try:
    import psycopg2
except ImportError:
    print("psycopg2 not installed")
    sys.exit(1)

def main():
    pg_url = os.getenv("TEST_PG_URL")
    if not pg_url:
        print("ERROR: TEST_PG_URL environment variable is not set.")
        sys.exit(1)

    try:
        conn = psycopg2.connect(pg_url, connect_timeout=10)
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            ver = cur.fetchone()[0]
            cur.execute("SELECT current_database();")
            dbname = cur.fetchone()[0]
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """)
            tables = [r[0] for r in cur.fetchall()]

        conn.close()
        print("SUCCESS: Connected to PostgreSQL database.")
        print(f"Database Name: {dbname}")
        print(f"Version: {ver.split(',')[0]}")
        print(f"Existing Public Tables ({len(tables)}): {', '.join(tables) if tables else 'None (Empty schema)'}")
    except Exception as e:
        # Sanitize exception message to avoid credential leaks
        err_msg = str(e)
        if "password" in err_msg.lower():
            err_msg = "Authentication failed (password rejected or connection refused)."
        print(f"CONNECTION ERROR: {err_msg}")
        sys.exit(2)

if __name__ == '__main__':
    main()
