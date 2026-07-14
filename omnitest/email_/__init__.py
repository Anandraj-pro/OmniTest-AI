"""Email testing with a swappable backend (SMTP/IMAP or Gmail API)."""
from __future__ import annotations

from omnitest.config import settings
from omnitest.email_.base import EmailClient, EmailMessage
from omnitest.email_.smtp_imap import SmtpImapClient


def make_email_client(backend: str | None = None) -> EmailClient:
    backend = backend or settings.email_backend
    if backend == "gmail_api":
        from omnitest.email_.gmail_api import GmailApiClient  # lazy: optional deps
        return GmailApiClient()
    return SmtpImapClient()


__all__ = ["EmailClient", "EmailMessage", "SmtpImapClient", "make_email_client"]