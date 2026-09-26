"""
Email service for DeepVision Django application.
Sends HTML verification and password reset emails via SMTP.
No plaintext passwords or secrets logged.
"""
import os
import smtplib
import logging
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# Ensure environment variables are loaded
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except Exception:
    pass


def _send_smtp_email(recipient_email, subject, html_content):
    """
    Sends HTML email via SMTP using environment configuration or Django settings.
    """
    mail_server = os.getenv("MAIL_SERVER") or os.getenv("SMTP_HOST") or os.getenv("EMAIL_HOST")
    mail_port = os.getenv("MAIL_PORT") or os.getenv("SMTP_PORT") or os.getenv("EMAIL_PORT") or "587"
    mail_username = os.getenv("MAIL_USERNAME") or os.getenv("SMTP_USERNAME") or os.getenv("EMAIL_HOST_USER")
    mail_password = (os.getenv("MAIL_PASSWORD") or os.getenv("SMTP_PASSWORD") or os.getenv("EMAIL_HOST_PASSWORD") or "").strip()
    mail_use_tls = (os.getenv("MAIL_USE_TLS") or os.getenv("SMTP_USE_TLS") or os.getenv("EMAIL_USE_TLS", "True")).lower() == "true"
    
    mail_sender = os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("SMTP_FROM") or os.getenv("DEFAULT_FROM_EMAIL")
    if not mail_sender or "yourgmail" in mail_sender:
        mail_sender = mail_username

    if not all([mail_server, mail_port, mail_username, mail_password]):
        logger.warning("[EMAIL] SMTP configuration incomplete. Email delivery skipped.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = mail_sender
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        port = int(mail_port)
        smtp_client = smtplib.SMTP(mail_server, port, timeout=10)
        if mail_use_tls:
            smtp_client.starttls()
        # Clean potential spaces in app passwords
        smtp_client.login(mail_username, mail_password)
        smtp_client.sendmail(mail_sender, recipient_email, msg.as_string())
        smtp_client.quit()
        logger.info(f"[EMAIL] Successfully sent '{subject}' to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL] SMTP transmission to {recipient_email} failed: {e}")
        return False


def send_verification_email(recipient_email, otp, full_name=None):
    """
    Sends email verification HTML message containing 6-digit OTP code.
    Accepts optional full_name parameter for personalization.
    """
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; padding: 20px; color: #333; line-height: 1.6;">
        <h2 style="color: #2b5c8f; border-bottom: 2px solid #2b5c8f; padding-bottom: 10px;">DeepVision</h2>
        <p>{greeting}</p>
        <p>Thank you for creating an account with DeepVision. To complete your registration, please verify your email address using the code below:</p>
        <div style="font-size: 28px; font-weight: bold; background-color: #f4f6f9; padding: 15px 25px; display: inline-block; letter-spacing: 4px; border-radius: 6px; border: 1px solid #e1e4e8; color: #2b5c8f; margin: 15px 0;">
          {otp}
        </div>
        <p>This verification code is valid for <strong>15 minutes</strong>. If you hit the attempt limit or the code expires, you will need to request a new code.</p>
        <p style="color: #666; font-size: 14px; margin-top: 25px;">If you did not initiate this registration, you can safely ignore this email.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin-top: 30px;">
        <p style="font-size: 11px; color: #999;">This is an automated message. Please do not reply to this email.</p>
      </body>
    </html>
    """
    return _send_smtp_email(recipient_email, "DeepVision - Email Verification", html_content)


def send_password_reset_email(recipient_email, otp, full_name=None):
    """
    Sends password reset HTML message containing 6-digit reset code.
    Accepts optional full_name parameter for personalization.
    """
    greeting = f"Hello {full_name}," if full_name else "Hello,"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; padding: 20px; color: #333; line-height: 1.6;">
        <h2 style="color: #2b5c8f; border-bottom: 2px solid #2b5c8f; padding-bottom: 10px;">DeepVision</h2>
        <p>{greeting}</p>
        <p>We received a request to reset the password for your DeepVision account.</p>
        <p>To proceed with resetting your password, please use the verification code below:</p>
        <div style="font-size: 28px; font-weight: bold; background-color: #f4f6f9; padding: 15px 25px; display: inline-block; letter-spacing: 4px; border-radius: 6px; border: 1px solid #e1e4e8; color: #d9534f; margin: 15px 0;">
          {otp}
        </div>
        <p>This password reset code is valid for <strong>15 minutes</strong>. If you hit the attempt limit or the code expires, you will need to submit a new reset request.</p>
        <p style="color: #666; font-size: 14px; margin-top: 25px;">If you did not request a password reset, you can safely ignore this email.</p>
        <hr style="border: 0; border-top: 1px solid #eee; margin-top: 30px;">
        <p style="font-size: 11px; color: #999;">This is an automated message. Please do not reply to this email.</p>
      </body>
    </html>
    """
    return _send_smtp_email(recipient_email, "DeepVision - Password Reset Verification", html_content)
