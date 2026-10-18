"""
Regression Test for Migration Script Safety Gates
Validates:
1. redact_url masks passwords completely.
2. Direct migration from live instance/deepvision.db with for_apply=True is strictly blocked.
3. Attempting to run --apply without --confirm-isolated-target exits with code 2.
"""
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath('.'))
from verification.migrate_sqlite_to_postgres import redact_url, get_sqlite_conn, main


class MigrationSafetyGateTests(unittest.TestCase):

    def test_redact_url(self):
        sample_url = "postgresql://postgres:super_secret_password_123@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        redacted = redact_url(sample_url)
        self.assertNotIn("super_secret_password_123", redacted)
        self.assertIn("aws-0-us-east-1.pooler.supabase.com:6543/postgres", redacted)
        self.assertIn("***:***", redacted)

    def test_live_database_blocked_for_apply(self):
        live_db = os.path.abspath("instance/deepvision.db")
        with self.assertRaises(PermissionError) as ctx:
            get_sqlite_conn(live_db, for_apply=True)
        self.assertIn("CRITICAL SAFETY VIOLATION", str(ctx.exception))

    def test_backup_database_allowed_for_apply(self):
        backup_db = os.path.abspath("verification/deepvision_backup_for_migration.db")
        conn = get_sqlite_conn(backup_db, for_apply=True)
        self.assertIsNotNone(conn)
        conn.close()

    @patch("sys.argv", ["migrate_sqlite_to_postgres.py", "--apply", "--pg-url", "postgresql://mock:mock@localhost:5432/mock"])
    def test_apply_without_isolated_confirmation_fails_closed(self):
        with self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 2)

    def test_repeat_run_abort_when_destination_populated(self):
        from unittest.mock import MagicMock
        from verification.migrate_sqlite_to_postgres import migrate_data
        mock_pg_conn = MagicMock()
        mock_pg_cur = MagicMock()
        mock_pg_conn.cursor.return_value = mock_pg_cur
        # Simulate table exists and count > 0
        mock_pg_cur.fetchone.side_effect = [(True,), (15,)]
        mock_sqlite_conn = MagicMock()

        source_stats = {"users": {"count": 15, "columns": ["id", "email"]}}
        with self.assertRaises(RuntimeError) as ctx:
            migrate_data(mock_sqlite_conn, mock_pg_conn, source_stats, drop_first=False)
        self.assertIn("REPEAT-RUN SAFETY ABORT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
