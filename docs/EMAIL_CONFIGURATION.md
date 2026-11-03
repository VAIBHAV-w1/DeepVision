# Email delivery configuration

DeepVision sends OTP email through Django's configured email backend. High and critical alert email is sent from the existing alert worker, subject to the user's notification preferences. No SMTP credentials belong in source control.

## Configure SMTP locally

1. Copy `.env.example` to the repository root as `.env` if a local environment file does not already exist.
2. Set these values in `.env`:
   - `MAIL_SERVER`: provider SMTP hostname.
   - `MAIL_PORT`: provider port, commonly `587` for STARTTLS or `465` for SSL.
   - `MAIL_USERNAME` and `MAIL_PASSWORD`: provider-issued SMTP credentials. For Gmail, use an app password, not the account password.
   - `MAIL_USE_TLS=True` and `MAIL_USE_SSL=False` for STARTTLS, or `MAIL_USE_TLS=False` and `MAIL_USE_SSL=True` for implicit SSL. Do not enable both.
   - `MAIL_DEFAULT_SENDER`: sender address accepted by the provider.
   - `MAIL_TIMEOUT`: connection/send timeout in seconds; defaults to 8.
3. Restart Django after changing `.env`; Django reads these settings at process startup.
4. Keep `.env` local. `.gitignore` excludes `.env` and `.env.*`; inspect `git status` before committing configuration changes.

OTP endpoints return delivery errors when the email backend rejects a message. Signup still creates the pending account and opens the verification screen, where the operator can retry delivery. Forgot-password responses remain generic to avoid account enumeration. Authentication mail is sent synchronously with a timeout so the API does not claim delivery before the provider accepts the message. Surveillance alert mail runs in the separate alert worker and never blocks frame capture or inference.

## Check SMTP connectivity without sending a message

From `deepvision_django/`, run:

```powershell
..\venv\Scripts\python.exe manage.py shell -c "from django.core.mail import get_connection; from django.conf import settings; c=get_connection(fail_silently=False, timeout=settings.EMAIL_TIMEOUT); print('authenticated' if c.open() else 'not connected'); c.close()"
```

This opens the SMTP connection and authenticates, but sends no email. A real OTP delivery test requires an authorized test mailbox; alert delivery should be tested with an authorized mailbox and a controlled high/critical event.
