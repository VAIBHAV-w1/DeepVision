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

    def test_soc_triage_sanitize_untrusted_text_is_linear_redos_safe(self):
        import time
        from apps.alerts.soc_triage import sanitize_untrusted_text

        for evil in ("<A" * 25000, "<" + (" " * 50000), "<script>alert(1)</script>Cam 01"):
            t0 = time.perf_counter()
            clean, _ = sanitize_untrusted_text(evil)
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 0.35, f"Regex took too long ({elapsed:.3f}s) for payload len={len(evil)}")
            self.assertNotIn("<script", clean.lower())

    def test_open_redirect_guards_reject_external_and_protocol_relative_targets(self):
        from types import SimpleNamespace
        from apps.accounts.decorators import _safe_next_path, login_required
        from apps.alerts.views import _safe_local_redirect_target

        rf = RequestFactory()
        evil_req = rf.get("/placeholder", HTTP_HOST="testserver")
        evil_req.get_full_path = lambda: "//evil.example.com/phish?x=1"
        evil_req.user = SimpleNamespace(is_authenticated=False)
        self.assertEqual(_safe_next_path(evil_req), "/")

        scheme_req = rf.get("/placeholder", HTTP_HOST="testserver")
        scheme_req.get_full_path = lambda: "https://evil.example.com/steal"
        self.assertEqual(_safe_next_path(scheme_req), "/")

        @login_required
        def protected(request):
            return None

        resp = protected(evil_req)
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("//evil.example.com", resp["Location"])

        bad_ref = rf.post("/alerts/5/ack/", HTTP_HOST="testserver", HTTP_REFERER="https://evil.example.com/steal")
        self.assertEqual(_safe_local_redirect_target(bad_ref, "/alerts/5/"), "/alerts/5/")

        good_ref = rf.post("/alerts/5/ack/", HTTP_HOST="testserver", HTTP_REFERER="http://testserver/alerts/?status=new")
        self.assertEqual(_safe_local_redirect_target(good_ref, "/alerts/5/"), "/alerts/?status=new")

    def test_session_password_fingerprint_and_middleware_revocation(self):
        from apps.accounts.middleware import AuthenticationMiddleware, compute_session_password_fingerprint

        fp1 = compute_session_password_fingerprint("pbkdf2_sha256$600000$salt$hashA")
        fp2 = compute_session_password_fingerprint("pbkdf2_sha256$600000$salt$hashB")
        self.assertEqual(len(fp1), 16)
        self.assertNotEqual(fp1, fp2)

        req = self.rf.get("/api/dashboard/")
        req.session = MagicMock()
        req.session.get.side_effect = lambda k, d=None: {"user_id": 7, "pw_fp": "outdated00000000"}.get(k, d)
        fake_user = MagicMock(id=7, is_active=True, password_hash="pbkdf2_sha256$600000$salt$hashA")

        mw = AuthenticationMiddleware(lambda r: r)
        with patch("apps.accounts.middleware.User.objects.filter") as mock_flt:
            mock_flt.return_value.first.return_value = fake_user
            mw(req)
        req.session.flush.assert_called_once()
        self.assertFalse(req.user.is_authenticated)

    def test_security_headers_middleware_and_spa_csp_hardening(self):
        import tempfile
        from pathlib import Path
        from django.http import JsonResponse
        from django.test import override_settings
        from apps.accounts.middleware import SecurityHeadersMiddleware
        from apps.core.views import react_app_view

        req_api = self.rf.get("/api/health/live/")
        mw = SecurityHeadersMiddleware(lambda r: JsonResponse({"status": "alive"}))
        resp_api = mw(req_api)
        self.assertEqual(resp_api["Permissions-Policy"], "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
        self.assertEqual(resp_api["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(resp_api["Cross-Origin-Resource-Policy"], "same-origin")
        self.assertIn("default-src 'none'", resp_api["Content-Security-Policy"])
        self.assertEqual(resp_api["Cache-Control"], "no-store, private")

        with tempfile.TemporaryDirectory() as tmpdir:
            dist_dir = Path(tmpdir) / "static" / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            (dist_dir / "index.html").write_text("<html><body><div id='root'></div></body></html>", encoding="utf-8")
            with override_settings(BASE_DIR=Path(tmpdir)):
                req_root = self.rf.get("/")
                resp_root = react_app_view(req_root)
        csp = resp_root.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("'unsafe-inline'", csp.split("script-src", 1)[1].split(";", 1)[0])
        self.assertIn("base-uri 'self'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertIn("object-src 'none'", csp)

    def test_internal_exceptions_are_not_exposed_in_api_errors(self):
        import json
        from types import SimpleNamespace
        from apps.core.api import api_clip_settings
        from apps.surveillance.audio.service import inspect_media_audio

        req = self.rf.post(
            "/api/settings/clip/",
            data=json.dumps({"cosine_threshold": 0.3}),
            content_type="application/json",
        )
        req.user = SimpleNamespace(id=1, is_authenticated=True, role="admin", is_superuser=True)
        fake_analyzer = MagicMock()
        fake_analyzer.update_config.side_effect = ValueError("secret-internal-path=/var/lib/db")
        with patch("apps.surveillance.ai.clip_service.get_clip_analyzer", return_value=fake_analyzer):
            resp = api_clip_settings(req)
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("secret-internal-path", resp.content.decode("utf-8"))

        with patch("apps.surveillance.audio.service.os.path.exists", return_value=True), patch(
            "builtins.open", side_effect=RuntimeError("/internal/secret/disk/path.mp4")
        ):
            audio_res = inspect_media_audio("clip.mp4")
        self.assertNotIn("path.mp4", audio_res.get("reason", ""))

    def test_wsgi_hardened_static_handler_sets_security_headers(self):
        from django.http import HttpResponse
        from config.wsgi import _HardenedStaticFilesHandler

        handler = _HardenedStaticFilesHandler(lambda environ, start_response: None)
        req = self.rf.get("/static/dist/theme-init.js", HTTP_X_FORWARDED_PROTO="https")
        with patch("django.contrib.staticfiles.handlers.StaticFilesHandler.get_response", return_value=HttpResponse("ok")):
            resp = handler.get_response(req)
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp["Permissions-Policy"], "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
        self.assertEqual(resp["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertEqual(resp["Cross-Origin-Resource-Policy"], "same-origin")


