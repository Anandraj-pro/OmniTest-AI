"""EmailClient interface + AI content/context verification, shared by all backends."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from omnitest.ai.agents import EmailAnalyzerAgent
from omnitest.utils.retry import retry


@dataclass(slots=True)
class EmailMessage:
    uid: str
    sender: str
    to: str
    subject: str
    body: str
    received_at: str = ""
    raw: Any = field(default=None, repr=False)


class EmailClient(abc.ABC):
    """Backends implement send/search; AI checks live on the base class."""

    def __init__(self) -> None:
        self._ai = EmailAnalyzerAgent()

    # ── backend responsibilities ────────────────────────
    @abc.abstractmethod
    def send(self, *, to: str, subject: str, body: str, html: bool = False) -> None: ...

    @abc.abstractmethod
    def search(self, *, subject_contains: str = "", from_contains: str = "",
               limit: int = 10) -> list[EmailMessage]: ...

    # ── shared convenience ──────────────────────────────
    def wait_for(
        self, *, subject_contains: str = "", from_contains: str = "",
        timeout: float = 90.0, interval: float = 5.0,
    ) -> EmailMessage:
        """Poll the inbox until a matching message arrives (or raise)."""

        @retry(timeout=timeout, interval=interval, on=(LookupError,))
        def _poll() -> EmailMessage:
            hits = self.search(subject_contains=subject_contains,
                               from_contains=from_contains, limit=5)
            if not hits:
                raise LookupError("no matching email yet")
            return hits[0]

        return _poll()

    # ── AI-driven checks (delegated to EmailAnalyzerAgent) ──
    def verify_content(self, msg: EmailMessage, expectation: str) -> dict[str, Any]:
        return self._ai.verify(subject=msg.subject, body=msg.body, expectation=expectation)

    def extract(self, msg: EmailMessage, fields: list[str]) -> dict[str, Any]:
        return self._ai.extract(body=msg.body, fields=fields)