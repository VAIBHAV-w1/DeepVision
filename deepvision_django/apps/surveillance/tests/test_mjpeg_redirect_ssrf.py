import os
import ssl
import socket
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.surveillance.camera.capture import (
    DummyVideoCapture,
    HttpMjpegCapture,
    _SafeMjpegRedirectHandler,
    _ScopedMjpegHTTPSHandler,
    _is_authorized_private_lan_url,
    safe_open_video_capture,
)


class HttpMjpegRedirectAndTlsSecurityTests(SimpleTestCase):
    def _dummy_request(self, url: str, headers: dict | None = None) -> urllib.request.Request:
        req = urllib.request.Request(url, headers=headers or {})
        return req

    def test_blocks_redirects_to_loopback_link_local_metadata_and_internal_targets(self):
        handler = _SafeMjpegRedirectHandler()
        origin_req = self._dummy_request(
            "http://192.168.1.50:8080/videofeed",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        fp = MagicMock()

        unsafe_targets = [
            "http://127.0.0.1:8000/admin",
            "http://[::1]:8000/secret",
            "http://[::ffff:127.0.0.1]:8000/internal",
            "http://localhost/health",
            "http://sub.localhost/api",
            "http://169.254.169.254/latest/meta-data/",
            "//169.254.169.254/latest/meta-data/",
            "http://[::ffff:169.254.169.254]/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://instance-data/latest/meta-data/",
            "http://internal-service.internal/metrics",
            "http://0.0.0.0:8000/",
            "file:///etc/passwd",
            "rtsp://127.0.0.1:554/live",
        ]

        for target in unsafe_targets:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    handler.redirect_request(origin_req, fp, 302, "Found", {}, target)

    def test_blocks_dns_rebinding_redirect_to_loopback_or_metadata(self):
        handler = _SafeMjpegRedirectHandler()
        origin_req = self._dummy_request("http://192.168.1.50:8080/videofeed")
        fp = MagicMock()

        with patch("apps.surveillance.camera.sources.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
            ]
            with self.assertRaises(ValueError):
                handler.redirect_request(origin_req, fp, 302, "Found", {}, "http://rebind.cam.example/stream")

            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
            ]
            with self.assertRaises(ValueError):
                handler.redirect_request(origin_req, fp, 302, "Found", {}, "http://meta-alias.cam.example/stream")

    def test_allows_authorized_lan_redirect_and_strips_cross_origin_auth(self):
        handler = _SafeMjpegRedirectHandler()
        origin_req = self._dummy_request(
            "http://192.168.1.50:8080/videofeed",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        fp = MagicMock()

        # Same-origin relative redirect retains credentials
        same_origin_req = handler.redirect_request(origin_req, fp, 302, "Found", {}, "/mjpeg")
        self.assertEqual(same_origin_req.full_url, "http://192.168.1.50:8080/mjpeg")
        self.assertTrue(same_origin_req.has_header("Authorization"))

        # Authorized second LAN camera hop is allowed, but strips Authorization header
        lan_hop_req = handler.redirect_request(
            origin_req, fp, 302, "Found", {}, "http://192.168.1.51:8080/videofeed"
        )
        self.assertEqual(lan_hop_req.full_url, "http://192.168.1.51:8080/videofeed")
        self.assertFalse(lan_hop_req.has_header("Authorization"))

    def test_enforces_max_redirect_hop_limit(self):
        handler = _SafeMjpegRedirectHandler()
        req = self._dummy_request("http://192.168.1.50:8080/videofeed")
        req._dv_redirect_hops = _SafeMjpegRedirectHandler.max_redirects
        fp = MagicMock()

        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(req, fp, 302, "Found", {}, "http://192.168.1.51:8080/videofeed")

    def test_capture_rejects_initial_and_redirected_ssrf_without_connecting(self):
        with patch("urllib.request.OpenerDirector.open") as mock_open:
            cap = HttpMjpegCapture("http://169.254.169.254/latest/meta-data/", timeout=1.0)
            self.assertFalse(cap.isOpened())
            self.assertIn("Security Error", cap.last_error or "")
            mock_open.assert_not_called()

        with patch("apps.surveillance.camera.sources.socket.getaddrinfo", return_value=[]):
            with patch("http.client.HTTPConnection.request") as mock_http_req:
                # Drive real handler validation inside opener against an unsafe redirect target
                handler = _SafeMjpegRedirectHandler()
                opener = urllib.request.build_opener(handler)
                req = urllib.request.Request("http://192.168.1.50:8080/videofeed")
                with patch.object(
                    urllib.request.HTTPHandler,
                    "http_open",
                    side_effect=lambda r: handler.redirect_request(
                        r, MagicMock(), 302, "Found", {}, "http://127.0.0.1:8000/secret"
                    ),
                ):
                    with self.assertRaises(ValueError):
                        opener.open(req, timeout=1.0)
                mock_http_req.assert_not_called()

    def test_self_signed_tls_is_disabled_by_default_and_strictly_lan_scoped(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPVISION_ALLOW_SELF_SIGNED_LAN_CAMERA", None)
            default_handler = _ScopedMjpegHTTPSHandler()
            self.assertFalse(default_handler.allow_self_signed_lan)
            with patch.object(default_handler, "do_open", return_value=MagicMock()) as mock_do_open:
                default_handler.https_open(self._dummy_request("https://192.168.1.50:8443/videofeed"))
                ctx = mock_do_open.call_args.kwargs["context"]
                self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(ctx.check_hostname)

        # Explicitly opted-in: relaxed ONLY for RFC1918 LAN targets, NEVER public hosts
        opted_in_handler = _ScopedMjpegHTTPSHandler(allow_self_signed_lan=True)
        with patch.object(opted_in_handler, "do_open", return_value=MagicMock()) as mock_do_open:
            opted_in_handler.https_open(self._dummy_request("https://192.168.1.50:8443/videofeed"))
            lan_ctx = mock_do_open.call_args.kwargs["context"]
            self.assertEqual(lan_ctx.verify_mode, ssl.CERT_NONE)
            self.assertFalse(lan_ctx.check_hostname)

            with patch("apps.surveillance.camera.capture.socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                ]
                opted_in_handler.https_open(self._dummy_request("https://public.camera.example/videofeed"))
                pub_ctx = mock_do_open.call_args.kwargs["context"]
                self.assertEqual(pub_ctx.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(pub_ctx.check_hostname)

        self.assertTrue(_is_authorized_private_lan_url("https://10.0.0.25/videofeed"))
        self.assertTrue(_is_authorized_private_lan_url("https://172.16.4.10/videofeed"))
        self.assertFalse(_is_authorized_private_lan_url("https://127.0.0.1/videofeed"))
        self.assertFalse(_is_authorized_private_lan_url("https://169.254.169.254/latest"))

    def test_safe_open_video_capture_never_falls_back_to_opencv_after_policy_rejection(self):
        with patch("apps.surveillance.camera.sources.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            ]
            with (
                patch("urllib.request.OpenerDirector.open", side_effect=ValueError("Security Error: unsafe redirect")),
                patch("apps.surveillance.camera.capture.cv2.VideoCapture") as mock_cv_cap,
            ):
                cap = safe_open_video_capture("https://public.camera.example/live")
                self.assertIsInstance(cap, DummyVideoCapture)
                self.assertFalse(cap.isOpened())
                mock_cv_cap.assert_not_called()

            with (
                patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError(ssl.SSLCertVerificationError("bad cert"))),
                patch("apps.surveillance.camera.capture.cv2.VideoCapture") as mock_cv_cap,
            ):
                cap = safe_open_video_capture("https://public.camera.example/live")
                self.assertIsInstance(cap, DummyVideoCapture)
                self.assertFalse(cap.isOpened())
                mock_cv_cap.assert_not_called()

