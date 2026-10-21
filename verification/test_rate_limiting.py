"""
DeepVision Automated Rate Limiting Verification Suite.
Verifies backend-enforced rate limiting returns HTTP 429 Too Many Requests
and compliant Retry-After headers under abuse-sensitive conditions.
"""

import os
import sys
import unittest
from django.test import RequestFactory
from django.http import JsonResponse

# Setup Django
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "deepvision_django"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from apps.core.rate_limiter import ratelimit, check_rate_limit, get_client_ip
from apps.core.models import AuditLog


class RateLimitingTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.test_ip = "192.0.2.42"

    def tearDown(self):
        AuditLog.objects.filter(ip_address=self.test_ip).delete()

    def test_01_client_ip_resolution(self):
        req = self.factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.195, 10.0.0.1")
        self.assertEqual(get_client_ip(req), "203.0.113.195")

        req2 = self.factory.get("/", HTTP_X_REAL_IP="198.51.100.7")
        self.assertEqual(get_client_ip(req2), "198.51.100.7")

        req3 = self.factory.get("/", REMOTE_ADDR="127.0.0.1")
        self.assertEqual(get_client_ip(req3), "127.0.0.1")

    def test_02_rate_limit_allows_under_threshold(self):
        req = self.factory.post("/api/auth/login/", REMOTE_ADDR=self.test_ip)
        is_limited, retry_after = check_rate_limit(req, "test_allow", limit=5, window_seconds=60)
        self.assertFalse(is_limited)
        self.assertEqual(retry_after, 0)

    def test_03_rate_limit_blocks_exceeding_threshold_with_429(self):
        @ratelimit(scope="test_block", limit=3, window=60)
        def dummy_view(request):
            return JsonResponse({"success": True})

        # Send 3 allowed requests
        for i in range(3):
            req = self.factory.post("/api/test/", REMOTE_ADDR=self.test_ip)
            resp = dummy_view(req)
            self.assertEqual(resp.status_code, 200)

        # 4th request MUST return HTTP 429
        req4 = self.factory.post("/api/test/", REMOTE_ADDR=self.test_ip)
        resp4 = dummy_view(req4)
        self.assertEqual(resp4.status_code, 429)
        self.assertIn("Retry-After", resp4.headers)
        self.assertGreater(int(resp4.headers["Retry-After"]), 0)


if __name__ == "__main__":
    unittest.main()
