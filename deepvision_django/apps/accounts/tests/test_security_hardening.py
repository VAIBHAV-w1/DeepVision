from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.accounts import views as auth_views
from apps.core.audit import get_client_ip as audit_get_client_ip
from apps.core.storage_service import (
    S3CompatibleStorageBackend,
    SupabaseStorageBackend,
    _safe_attachment_filename,
)


class SecurityHardeningRegressionTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_audit_get_client_ip_ignores_spoofed_x_forwarded_for(self):
        req = self.rf.get(
            "/api/auth/login/",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.77",
            HTTP_TRUE_CLIENT_IP="5.6.7.8",
            HTTP_X_REAL_IP="9.9.9.9",
            REMOTE_ADDR="10.0.0.2",
        )
        # Must trust right-most non-private proxy hop, never client-spoofed left-most IP
        self.assertEqual(audit_get_client_ip(req), "198.51.100.77")

    def test_obsolete_password_only_legacy_auth_views_removed(self):
        self.assertFalse(hasattr(auth_views, "login_view"))
        self.assertFalse(hasattr(auth_views, "signup_view"))
        self.assertFalse(hasattr(auth_views, "forgot_password_view"))
        self.assertFalse(hasattr(auth_views, "reset_password_view"))
        self.assertTrue(callable(auth_views.validate_password_strength))
        self.assertTrue(callable(auth_views.logout_view))

    def test_cloud_storage_attachment_filename_strips_header_injection(self):
        cleaned = _safe_attachment_filename('../../evil\r\nSet-Cookie: a=b"clip.mp4')
        self.assertEqual(cleaned, "evilSet-Cookie: a=bclip.mp4")
        self.assertEqual(_safe_attachment_filename('bad"\r\nX-Injected: yes/clip.mp4'), "clip.mp4")
        self.assertNotIn("\r", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn('"', cleaned)

        mock_upstream = MagicMock()
        mock_upstream.status_code = 200
        mock_upstream.headers = {"Content-Length": "4", "Accept-Ranges": "bytes"}
        mock_upstream.iter_content.return_value = [b"data"]

        supa = SupabaseStorageBackend("https://example.supabase.co", "service-key")
        s3 = S3CompatibleStorageBackend("bucket", "ak", "sk", endpoint_url="https://s3.example.com")
        req = self.rf.get("/recordings/1/download/")

        with patch("apps.core.storage_service.requests.get", return_value=mock_upstream):
            resp1 = supa.open_range_response(
                req,
                "deepvision-recordings",
                "u1/cam1/clip.mp4",
                "video/mp4",
                as_attachment=True,
                download_name='bad"\r\nX-Injected: yes/clip.mp4',
            )
            resp2 = s3.open_range_response(
                req,
                "bucket",
                "u1/cam1/clip.mp4",
                "video/mp4",
                as_attachment=True,
                download_name='bad"\r\nX-Injected: yes/clip.mp4',
            )

        for resp in (resp1, resp2):
            cd = resp["Content-Disposition"]
            self.assertNotIn("\r", cd)
            self.assertNotIn("\n", cd)
            self.assertEqual(cd.count('"'), 2)

    def test_assistant_chat_rejects_oversized_message_and_enforces_rate_limit(self):
        import json
        from types import SimpleNamespace
        from apps.core.views import assistant_chat_view

        req_long = self.rf.post(
            "/api/assistant/chat/",
            data=json.dumps({"message": "A" * 1001}),
            content_type="application/json",
        )
        req_long.user = SimpleNamespace(id=1, is_authenticated=True, role="user")
        with patch("apps.core.rate_limiter.check_rate_limit", return_value=(False, 0)):
            resp_long = assistant_chat_view(req_long)
        self.assertEqual(resp_long.status_code, 400)

        req_ok = self.rf.post(
            "/api/assistant/chat/",
            data=json.dumps({"message": "How do I add a camera?"}),
            content_type="application/json",
        )
        req_ok.user = SimpleNamespace(id=1, is_authenticated=True, role="user")
        with patch("apps.core.rate_limiter.check_rate_limit", return_value=(True, 45)):
            resp_limited = assistant_chat_view(req_ok)
        self.assertEqual(resp_limited.status_code, 429)
        self.assertEqual(resp_limited["Retry-After"], "45")

    def test_invalidate_camera_zones_does_not_bind_unrelated_workers(self):
        from apps.core.api import _invalidate_camera_zones

        worker_a = MagicMock()
        worker_b = MagicMock()
        fake_reg = MagicMock()
        fake_reg.physical_workers = {"src_a": worker_a, "src_b": worker_b}
        fake_reg.workers = {101: worker_a, 202: worker_b}
        fake_reg.get_active_worker.side_effect = lambda cid: {101: worker_a, 202: worker_b}.get(cid)

        with patch("apps.surveillance.ai.registry.get_inference_registry", return_value=fake_reg):
            _invalidate_camera_zones(101)

        worker_a.invalidate_zones.assert_called_once_with()
        worker_a.bind_camera.assert_not_called()
        worker_b.invalidate_zones.assert_not_called()
        worker_b.bind_camera.assert_not_called()

    def test_verify_model_artifact_rejects_unmanifested_filename(self):
        import tempfile
        from pathlib import Path
        from apps.surveillance.ai.onnx_runtime import verify_model_artifact

        with tempfile.TemporaryDirectory() as tmpd:
            f = Path(tmpd) / "untrusted_custom.onnx"
            f.write_bytes(b"fake-onnx")
            ok, msg, digest = verify_model_artifact(str(f))
            self.assertFalse(ok)
            self.assertIn("Unregistered", msg)
            self.assertIsNotNone(digest)
