from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.accounts.email_service import send_security_alert_email, send_verification_email
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
