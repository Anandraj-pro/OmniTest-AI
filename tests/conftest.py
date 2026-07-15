"""Shared pytest fixtures for OmniTest-AI (Playwright + pytest primary stack)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import allure
import pytest
from playwright.sync_api import Page

from omnitest.api import ApiClient
from omnitest.ai.agents import (
    ApiValidatorAgent,
    EmailAnalyzerAgent,
    FailureAnalystAgent,
    TestGeneratorAgent,
)
from omnitest.ai.context import set_story
from omnitest.email_ import make_email_client
from omnitest.ui import BasePage

ARTIFACTS = Path("artifacts")


# ── Story attribution: @pytest.mark.story("OMNI-142") ───
@pytest.fixture(autouse=True)
def _story_context(request):
    """Bind the test's story ID to the AI context and the Allure label, so both
    the prompt tracker and Allure results carry it for the director dashboard.
    """
    marker = request.node.get_closest_marker("story")
    story_id = marker.args[0] if marker and marker.args else None
    set_story(story_id)
    if story_id:
        try:
            import allure

            allure.dynamic.label("story", story_id)
        except Exception:  # pragma: no cover - allure optional at runtime
            pass
    yield
    set_story(None)


# ── adapters ────────────────────────────────────────────
@pytest.fixture
def api() -> Iterator[ApiClient]:
    client = ApiClient()
    yield client
    client.close()


@pytest.fixture
def email():
    return make_email_client()


# ── AI agents ───────────────────────────────────────────
@pytest.fixture(scope="session")
def api_ai() -> ApiValidatorAgent:
    return ApiValidatorAgent()


@pytest.fixture(scope="session")
def email_ai() -> EmailAnalyzerAgent:
    return EmailAnalyzerAgent()


@pytest.fixture(scope="session")
def failure_ai() -> FailureAnalystAgent:
    return FailureAnalystAgent()


@pytest.fixture(scope="session")
def gen() -> TestGeneratorAgent:
    return TestGeneratorAgent()


# ── UI: wrap pytest-playwright's `page` with AI self-healing ──
@pytest.fixture
def ai_page(page: Page) -> BasePage:
    return BasePage(page, self_heal=True)


# ── Allure: attach a screenshot on UI-test failure ──────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):  # type: ignore[no-untyped-def]
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page is not None:
            ARTIFACTS.mkdir(exist_ok=True)
            shot = ARTIFACTS / f"{item.name}.png"
            try:
                page.screenshot(path=str(shot))
                allure.attach.file(str(shot), name="screenshot",
                                   attachment_type=allure.attachment_type.PNG)
            except Exception:  # pragma: no cover
                pass