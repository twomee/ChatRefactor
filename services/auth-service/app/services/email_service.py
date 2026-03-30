# app/services/email_service.py — Email sender abstraction with SMTP and console implementations
"""
Provides a pluggable email sender:
- ConsoleEmailSender: logs emails to stdout (used when SMTP is not configured)
- SMTPEmailSender: sends real emails via SMTP with STARTTLS

Factory function create_email_sender() picks the right implementation based on
environment variables. If SMTP_HOST is set, it uses SMTP; otherwise it falls
back to console mode so that development and tests work without an SMTP server.
"""

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    """Abstract base class for email sending."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> None:
        """Send an email to the given recipient."""
        ...


class ConsoleEmailSender(EmailSender):
    """Logs emails to console — used when SMTP is not configured."""

    def send(self, to: str, subject: str, body: str) -> None:
        # Sanitize user-provided values to prevent log injection
        safe_to = to.replace("\n", "\\n").replace("\r", "\\r")
        safe_subject = subject.replace("\n", "\\n").replace("\r", "\\r")
        safe_body = body.replace("\n", "\\n").replace("\r", "\\r")
        logger.info(
            "=== EMAIL (console mode) ===\n"
            "To: %s\nSubject: %s\n%s\n"
            "===========================",
            safe_to,
            safe_subject,
            safe_body,
        )


class SMTPEmailSender(EmailSender):
    """Sends real emails via SMTP with STARTTLS."""

    def __init__(
        self, host: str, port: int, username: str, password: str, from_addr: str
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr

    def send(self, to: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = to
        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)


def create_email_sender() -> EmailSender:
    """Factory: build the right EmailSender based on environment variables."""
    host = os.getenv("SMTP_HOST")
    if host:
        return SMTPEmailSender(
            host=host,
            port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            from_addr=os.getenv("SMTP_FROM", "noreply@chatbox.local"),
        )
    return ConsoleEmailSender()
