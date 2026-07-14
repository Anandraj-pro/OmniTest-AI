"""Gmail-API backend (optional). Install extras: pip install '.[gmail]'.

Uses OAuth credentials from settings.gmail_credentials / gmail_token.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage as PyEmailMessage

from omnitest.config import settings
from omnitest.email_.base import EmailClient, EmailMessage
from omnitest.utils.logger import get_logger

log = get_logger("email.gmail_api")
_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class GmailApiClient(EmailClient):
    def __init__(self) -> None:
        super().__init__()
        self._service = self._build_service()

    def _build_service(self):  # type: ignore[no-untyped-def]
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if settings.gmail_token.exists():
            creds = Credentials.from_authorized_user_file(str(settings.gmail_token), _SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(settings.gmail_credentials), _SCOPES)
                creds = flow.run_local_server(port=0)
            settings.gmail_token.parent.mkdir(parents=True, exist_ok=True)
            settings.gmail_token.write_text(creds.to_json())
        return build("gmail", "v1", credentials=creds)

    def send(self, *, to: str, subject: str, body: str, html: bool = False) -> None:
        m = PyEmailMessage()
        m["To"] = to
        m["From"] = settings.email_user
        m["Subject"] = subject
        m.set_content(body, subtype="html" if html else "plain")
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        self._service.users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("sent %r to %s", subject, to)

    def search(self, *, subject_contains: str = "", from_contains: str = "",
               limit: int = 10) -> list[EmailMessage]:
        q = []
        if subject_contains:
            q.append(f'subject:"{subject_contains}"')
        if from_contains:
            q.append(f"from:{from_contains}")
        resp = self._service.users().messages().list(
            userId="me", q=" ".join(q) or None, maxResults=limit).execute()
        out: list[EmailMessage] = []
        for ref in resp.get("messages", []):
            full = self._service.users().messages().get(
                userId="me", id=ref["id"], format="full").execute()
            out.append(self._to_message(full))
        return out

    @staticmethod
    def _to_message(full: dict) -> EmailMessage:  # type: ignore[type-arg]
        headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
        body = GmailApiClient._extract_body(full["payload"])
        return EmailMessage(
            uid=full["id"],
            sender=headers.get("from", ""),
            to=headers.get("to", ""),
            subject=headers.get("subject", ""),
            body=body,
            received_at=headers.get("date", ""),
            raw=full,
        )

    @staticmethod
    def _extract_body(payload: dict) -> str:  # type: ignore[type-arg]
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "replace")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        for part in payload.get("parts", []):
            nested = GmailApiClient._extract_body(part)
            if nested:
                return nested
        return ""