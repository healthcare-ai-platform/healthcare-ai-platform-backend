import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from botocore.exceptions import ClientError

from app.core.config import APP_BASE_URL, SES_FROM_EMAIL

logger = logging.getLogger("healthcare-platform")


def send_invite_email(to_email: str, name: str, token: str, role: str) -> None:
    invite_url = f"{APP_BASE_URL}/accept-invite?token={token}"
    subject = "You've been invited to Healthcare AI Platform"
    body_text = (
        f"Hi {name},\n\n"
        f"You've been invited as {role} on the Healthcare AI Platform.\n\n"
        f"Accept your invite here:\n{invite_url}\n\n"
        "This link expires in 48 hours."
    )
    body_html = f"""
<h2>You've been invited</h2>
<p>Hi {name},</p>
<p>You've been invited to the Healthcare AI Platform as <strong>{role}</strong>.</p>
<p><a href="{invite_url}" style="background:#185fa5;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;">Accept Invite</a></p>
<p style="margin-top:16px;color:#666;font-size:13px;">This link expires in 48 hours.</p>
"""

    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        _send_smtp(smtp_host, to_email, subject, body_text, body_html, invite_url)
    else:
        _send_ses(to_email, subject, body_text, body_html, invite_url)


def _send_smtp(smtp_host: str, to_email: str, subject: str, body_text: str, body_html: str, invite_url: str) -> None:
    host, _, port_str = smtp_host.partition(":")
    port = int(port_str) if port_str else 1025

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SES_FROM_EMAIL
    msg["To"]      = to_email
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.sendmail(SES_FROM_EMAIL, [to_email], msg.as_string())
        logger.info("Invite email sent via SMTP to %s", to_email)
    except Exception as exc:
        logger.warning("SMTP send failed for %s (%s). Invite URL: %s", to_email, exc, invite_url)


def _send_ses(to_email: str, subject: str, body_text: str, body_html: str, invite_url: str) -> None:
    kwargs: dict = {}
    endpoint_url = os.getenv("AWS_ENDPOINT_URL")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    try:
        ses = boto3.client(
            "ses",
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            **kwargs,
        )
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {
                    "Text": {"Data": body_text},
                    "Html": {"Data": body_html},
                },
            },
        )
        logger.info("Invite email sent via SES to %s", to_email)
    except ClientError as exc:
        logger.warning(
            "SES send failed for %s (%s). Invite URL: %s",
            to_email,
            exc.response["Error"]["Message"],
            invite_url,
        )
    except Exception as exc:
        logger.warning("Email send failed for %s (%s). Invite URL: %s", to_email, exc, invite_url)
