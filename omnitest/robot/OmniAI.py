"""OmniAI — Robot Framework keyword library exposing OmniTest-AI's AI + adapters.

Import in a suite:

    *** Settings ***
    Library    omnitest.robot.OmniAI

Keywords wrap the API client, email adapter, and AI agents so Robot suites (the
primary authoring layer) can drive AI-assisted checks directly.
"""
from __future__ import annotations

from typing import Any

from robot.api.deco import keyword, library

from omnitest.ai.agents import (
    ApiValidatorAgent,
    EmailAnalyzerAgent,
    FailureAnalystAgent,
    TestGeneratorAgent,
)
from omnitest.api import ApiClient
from omnitest.email_ import make_email_client


@library(scope="SUITE", auto_keywords=False)
class OmniAI:
    ROBOT_LIBRARY_VERSION = "0.1.0"

    def __init__(self) -> None:
        self._api = ApiClient()
        self._email = make_email_client()
        self._api_ai = ApiValidatorAgent()
        self._email_ai = EmailAnalyzerAgent()
        self._failure_ai = FailureAnalystAgent()
        self._gen = TestGeneratorAgent()

    # ── API ─────────────────────────────────────────────
    @keyword("Api Request")
    def api_request(self, method: str, url: str, **kwargs: Any) -> Any:
        return self._api.request(method, url, **kwargs)

    @keyword("Response Should Meet Expectation")
    def response_meets(self, response: Any, expectation: str) -> dict:
        verdict = self._api_ai.assess(
            response_json=response.json_str(), expectation=expectation, status=response.status
        )
        if not verdict.get("pass"):
            raise AssertionError(f"API expectation failed: {verdict.get('reason')} "
                                 f"| violations={verdict.get('violations')}")
        return verdict

    # ── Email ───────────────────────────────────────────
    @keyword("Send Email")
    def send_email(self, to: str, subject: str, body: str, html: bool = False) -> None:
        self._email.send(to=to, subject=subject, body=body, html=html)

    @keyword("Wait For Email")
    def wait_for_email(self, subject_contains: str = "", from_contains: str = "",
                       timeout: float = 90.0) -> Any:
        return self._email.wait_for(subject_contains=subject_contains,
                                    from_contains=from_contains, timeout=timeout)

    @keyword("Email Should Meet Expectation")
    def email_meets(self, message: Any, expectation: str) -> dict:
        verdict = self._email.verify_content(message, expectation)
        if not verdict.get("pass"):
            raise AssertionError(f"Email expectation failed: {verdict.get('reason')} "
                                 f"| missing={verdict.get('missing')}")
        return verdict

    @keyword("Extract From Email")
    def extract_email(self, message: Any, *fields: str) -> dict:
        return self._email.extract(message, list(fields))

    # ── AI generation / diagnosis ───────────────────────
    @keyword("Generate Robot Suite")
    def generate_robot(self, requirement: str) -> str:
        return self._gen.robot_suite(requirement)

    @keyword("Diagnose Failure")
    def diagnose(self, test: str, error: str, logs: str = "") -> dict:
        return self._failure_ai.diagnose(test=test, error=error, logs=logs)