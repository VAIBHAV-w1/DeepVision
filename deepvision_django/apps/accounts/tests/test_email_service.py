import json
import os
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.email_service import (
    confirm_email_delivered,
    get_email_runtime_status,
    reset_email_runtime_status,
    send_login_otp_email,
    send_security_alert_email,
    send_verification_email,
)
from apps.accounts.views import resend_otp_view, resend_reset_otp_view


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="smtp.example.test",
    EMAIL_PORT=587,
    EMAIL_HOST_USER="operator",
    EMAIL_HOST_PASSWORD="test-only",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False,
    DEFAULT_FROM_EMAIL="alerts@example.test",
    EMAIL_TIMEOUT=2,
)
class EmailServiceTests(SimpleTestCase):
    def setUp(self):
        mail.outbox = []

    def test_otp_email_uses_django_backend_and_escapes_name(self):
        self.assertTrue(send_verification_email("person@example.test", "012345", "<Operator>"))

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["person@example.test"])
        self.assertIn("012345", message.body)
        html = message.alternatives[0][0]
        self.assertIn("&lt;Operator&gt;", html)
        self.assertNotIn("<Operator>", html)

    @override_settings(EMAIL_HOST_PASSWORD="")
    def test_missing_smtp_credentials_report_delivery_failure(self):
        self.assertFalse(send_verification_email("person@example.test", "012345"))
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="", DEFAULT_FROM_EMAIL="DeepVision <noreply@example.test>")
    def test_resend_https_api_fallback_sends_valid_payload_and_headers(self):
        reset_email_runtime_status()
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b'{"id": "re_msg_12345"}'
        fake_resp.__enter__.return_value = fake_resp

        with patch.dict(os.environ, {"RESEND_API_KEY": "re_test_token_do_not_log"}, clear=False):
            with patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
                ok = send_login_otp_email("operator@example.test", "654321", "SOC Operator")

        self.assertTrue(ok)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.resend.com/emails")
        self.assertEqual(req.get_method(), "POST")
        headers_lower = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(headers_lower.get("authorization"), "Bearer re_test_token_do_not_log")
        self.assertEqual(headers_lower.get("content-type"), "application/json")
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["from"], "DeepVision <noreply@example.test>")
        self.assertEqual(payload["to"], ["operator@example.test"])
        self.assertEqual(payload["subject"], "DeepVision - Sign-In Verification Code")
        self.assertIn("654321", payload["html"])
        self.assertIn("654321", payload["text"])
        rt = get_email_runtime_status()
        self.assertTrue(rt["tested"])
        self.assertEqual(rt["last_status"], "provider_accepted")
        self.assertEqual(rt["last_provider"], "resend")
        self.assertEqual(rt["last_message_id"], "re_msg_12345")
        self.assertIsNone(rt["last_error_code"])

        confirm_email_delivered(provider="resend", message_id="re_msg_12345")
        rt_delivered = get_email_runtime_status()
        self.assertEqual(rt_delivered["last_status"], "delivered")

    @override_settings(EMAIL_HOST="", EMAIL_HOST_USER="", EMAIL_HOST_PASSWORD="", DEFAULT_FROM_EMAIL="DeepVision <noreply@example.test>")
    def test_resend_https_api_rejection_reports_failure_without_leaking_key(self):
        http_err = urllib.error.HTTPError(
            url="https://api.resend.com/emails",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        with patch.dict(os.environ, {"RESEND_API_KEY": "re_secret_key_value"}, clear=False):
            with patch("urllib.request.urlopen", side_effect=http_err):
                with self.assertLogs("apps.accounts.email_service", level="WARNING") as logs:
                    ok = send_login_otp_email("operator@example.test", "654321", "SOC Operator")

        self.assertFalse(ok)
        joined_logs = " ".join(logs.output)
        self.assertIn("status=403", joined_logs)
        self.assertNotIn("re_secret_key_value", joined_logs)
        self.assertNotIn("654321", joined_logs)
        rt = get_email_runtime_status()
        self.assertTrue(rt["tested"])
        self.assertEqual(rt["last_status"], "failed")
        self.assertEqual(rt["last_provider"], "resend")
        self.assertEqual(rt["last_error_code"], "HTTP_403")


    @patch("apps.accounts.models.User.objects.filter")
    @patch("apps.notifications.models.NotificationPreference.objects.filter")
    def test_high_critical_alert_email_uses_owner_and_alert_context(self, pref_filter, user_filter):
        pref_filter.return_value.first.return_value = None
        user_filter.return_value.only.return_value.first.return_value = SimpleNamespace(
            email="owner@example.test"
        )
        alert = SimpleNamespace(
            id=42,
            severity="critical",
            event_type="intrusion",
            title="Restricted area entry",
            message="Person entered the loading zone.",
            camera_id=4,
        )

        self.assertTrue(send_security_alert_email(7, alert))
        self.assertEqual(mail.outbox[0].to, ["owner@example.test"])
        body = mail.outbox[0].alternatives[0][0]
        self.assertIn("critical", body.lower())
        self.assertIn("Restricted area entry", body)
        self.assertIn("Event #42", body)

    @patch("apps.notifications.models.NotificationPreference.objects.filter")
    def test_low_severity_security_event_is_not_emailed(self, pref_filter):
        alert = SimpleNamespace(severity="low", event_type="loitering")
        self.assertFalse(send_security_alert_email(7, alert))
        pref_filter.assert_not_called()
        self.assertEqual(mail.outbox, [])


class LegacyOtpResendViewTests(SimpleTestCase):
    def _request(self, path, session):
        request = RequestFactory().post(path)
        request.session = session
        request._messages = FallbackStorage(request)
        return request

    def _assert_failure_message(self, request):
        messages = [str(message) for message in request._messages]
        self.assertTrue(any("Failed to send" in message for message in messages))
        self.assertFalse(any("has been sent" in message for message in messages))

    @patch("apps.accounts.views.send_verification_email", side_effect=RuntimeError("credential=secret"))
    @patch("apps.accounts.views.User.objects.filter")
    def test_resend_verification_does_not_claim_delivery_on_backend_failure(self, user_filter, send_email):
        user = Mock(id=12, email="operator@example.test", email_otp_sent_at=None)
        user.generate_otp.return_value = "012345"
        user_filter.return_value.first.return_value = user
        request = self._request("/resend-otp/", {"signup_email": user.email})

        with self.assertLogs("apps.accounts.views", level="WARNING") as logs:
            response = resend_otp_view(request)

        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once_with(user.email, "012345")
        user.save.assert_any_call(update_fields=["email_otp_sent_at"])
        self._assert_failure_message(request)
        self.assertNotIn("credential=secret", " ".join(logs.output))

    @patch("apps.accounts.views.send_password_reset_email", return_value=False)
    @patch("apps.accounts.views.User.objects.filter")
    def test_resend_reset_does_not_claim_delivery_on_backend_failure(self, user_filter, send_email):
        user = Mock(id=13, email="operator@example.test", password_reset_otp_sent_at=None)
        user.generate_reset_otp.return_value = "543210"
        user_filter.return_value.first.return_value = user
        request = self._request("/resend-reset-otp/", {"reset_email": user.email})

        response = resend_reset_otp_view(request)

        self.assertEqual(response.status_code, 302)
        send_email.assert_called_once_with(user.email, "543210")
        user.save.assert_any_call(update_fields=["password_reset_otp_sent_at"])
        self._assert_failure_message(request)
