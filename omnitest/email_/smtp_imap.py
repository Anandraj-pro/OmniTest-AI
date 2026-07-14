"""SMTP (send) + IMAP (receive) backend — works with any standard provider."""
from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage as PyEmailMessage

from omnitest.config import settings
from omnitest.email_.base import EmailClient, EmailMessage
from omnitest.utils.logger import get_logger

log = get_logger("email.smtp_imap")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def _body_of(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
        # fall back to first html part
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", "replace")


class SmtpImapClient(EmailClient):
    def send(self, *, to: str, subject: str, body: str, html: bool = False) -> None:
        m = PyEmailMessage()
        m["From"] = settings.email_user
        m["To"] = to
        m["Subject"] = subject
        m.set_content(body, subtype="html" if html else "plain")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.starttls()
            s.login(settings.email_user, settings.email_password)
            s.send_message(m)
        log.info("sent %r to %s", subject, to)

    def search(self, *, subject_contains: str = "", from_contains: str = "",
               limit: int = 10) -> list[EmailMessage]:
        conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        try:
            conn.login(settings.email_user, settings.email_password)
            conn.select("INBOX")
            criteria: list[str] = ["ALL"]
            if subject_contains:
                criteria = ["SUBJECT", f'"{subject_contains}"']
            if from_contains:
                criteria += ["FROM", f'"{from_contains}"']
            typ, data = conn.search(None, *criteria)
            ids = data[0].split()[-limit:][::-1] if data and data[0] else []
            out: list[EmailMessage] = []
            for mid in ids:
                typ, raw = conn.fetch(mid, "(RFC822)")
                if not raw or not raw[0]:
                    continue
                msg = email.message_from_bytes(raw[0][1])
                out.append(EmailMessage(
                    uid=mid.decode(),
                    sender=_decode(msg.get("From")),
                    to=_decode(msg.get("To")),
                    subject=_decode(msg.get("Subject")),
                    body=_body_of(msg),
                    received_at=_decode(msg.get("Date")),
                    raw=msg,
                ))
            return out
        finally:
            try:
                conn.logout()
            except Exception:  # pragma: no cover
                pass
