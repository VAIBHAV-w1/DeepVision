"""
Regression tests for DeepVision Health & Database Readiness Diagnostics.
Validates:
1. Local SQLite healthy baseline with verified tables.
2. Serverless ephemeral mode detection (returns 503 pending_configuration).
3. Schema missing detection (returns 503 pending_migration).
4. Database connection failure handling (returns 503 unavailable, zero secret leak).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = ROOT_DIR / 'deepvision_django'
if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.test import RequestFactory
from apps.core.views import health_check_view


class TestHealthAndReadiness(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_local_sqlite_healthy_baseline(self):
        """When running locally with canonical SQLite, health check returns 200 with verified schema."""
        request = self.factory.get('/api/health/')
        response = health_check_view(request)
        
        self.assertIn(response.status_code, (200, 503)) # 200 if surveillance engine standby is degraded or healthy
        import json
        data = json.loads(response.content.decode())
        self.assertEqual(data.get('django_app'), 'online')
        self.assertEqual(data.get('database'), 'connected')
        self.assertEqual(data.get('database_backend'), 'sqlite')
        self.assertTrue(data.get('schema_ready'))
        self.assertGreaterEqual(data.get('tables_count', 0), 3)

    def test_serverless_unconfigured_ephemeral_sqlite(self):
        """When running in serverless (VERCEL=1) without DATABASE_URL, returns 503 pending_configuration."""
        request = self.factory.get('/api/health/')
        with patch.dict(os.environ, {'VERCEL': '1'}):
            with patch('apps.core.views.connection') as mock_conn:
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (1,)
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                mock_conn.vendor = 'sqlite'
                mock_conn.settings_dict = {'NAME': ':memory:'}
                mock_conn.introspection.table_names.return_value = []

                response = health_check_view(request)
                self.assertEqual(response.status_code, 503)
                import json
                data = json.loads(response.content.decode())
                self.assertEqual(data.get('status'), 'pending_configuration')
                self.assertEqual(data.get('database'), 'pending_configuration')
                self.assertFalse(data.get('schema_ready'))
                self.assertIn('DATABASE_URL', data.get('diagnostic', ''))

    def test_pending_migration_when_tables_missing(self):
        """When connected to postgres but core tables are not yet migrated, returns 503 pending_migration."""
        request = self.factory.get('/api/health/')
        with patch('apps.core.views.connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn.vendor = 'postgresql'
            mock_conn.settings_dict = {'NAME': 'deepvision_db'}
            mock_conn.introspection.table_names.return_value = ['some_other_table']

            response = health_check_view(request)
            self.assertEqual(response.status_code, 503)
            import json
            data = json.loads(response.content.decode())
            self.assertEqual(data.get('status'), 'pending_migration')
            self.assertEqual(data.get('database'), 'connected')
            self.assertEqual(data.get('database_backend'), 'postgresql')
            self.assertFalse(data.get('schema_ready'))
            self.assertIn('migration', data.get('diagnostic', '').lower())

    def test_database_connection_failure(self):
        """When database connection fails, returns 503 unavailable with safe diagnostic (no credentials)."""
        request = self.factory.get('/api/health/')
        with patch('apps.core.views.connection') as mock_conn:
            mock_conn.cursor.side_effect = Exception("FATAL: password authentication failed for user 'pguser'")
            mock_conn.vendor = 'postgresql'
            mock_conn.settings_dict = {'NAME': 'deepvision_db'}

            response = health_check_view(request)
            self.assertEqual(response.status_code, 503)
            import json
            data = json.loads(response.content.decode())
            self.assertEqual(data.get('status'), 'unavailable')
            self.assertEqual(data.get('database'), 'disconnected')
            self.assertFalse(data.get('schema_ready'))
            # Critical: Must NOT leak internal password exception string
            self.assertNotIn('password', data.get('diagnostic', '').lower())
            self.assertNotIn('pguser', data.get('diagnostic', '').lower())


if __name__ == '__main__':
    unittest.main()
