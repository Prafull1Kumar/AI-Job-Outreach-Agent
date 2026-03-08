import os
import smtplib
from email.message import EmailMessage
from app.schemas import SendEmailResponse


def send_email_via_gmail(to_email: str, subject: str, body: str) -> SendEmailResponse:
    """
    Send email through Gmail SMTP.

    TODO(OUTREACH): If you prefer full Gmail API OAuth flow,
    replace SMTP logic with google-api-python-client integration.
    """
    sender = os.getenv("GMAIL_SENDER_EMAIL")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not app_password:
        return SendEmailResponse(
            status="skipped",
            message="Missing Gmail credentials. Fill backend/.env first.",
        )

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, app_password)
            smtp.send_message(msg)

        return SendEmailResponse(status="success", message=f"Email sent to {to_email}")
    except Exception as exc:
        return SendEmailResponse(status="failed", message=str(exc))
