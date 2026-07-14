"""Reusable pytest-bdd steps — the throughput multiplier at 50+ stories/sprint.

Most stories reuse these steps, so a new `.feature` often needs ZERO new Python.
Only write story-specific steps when a scenario needs behaviour not covered here.

Covers three flows:
    • API    — call an endpoint, assert status/shape, AI semantic check
    • UI     — navigate, click, fill, assert (self-healing via `ai_page`)
    • Email  — send, wait for arrival, AI content verification

Shared state between steps travels in the `ctx` dict fixture.
"""
from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, when, then, parsers

from omnitest.email_.base import EmailMessage


@pytest.fixture
def ctx() -> dict[str, Any]:
    """Per-scenario scratch space shared across steps."""
    return {}


# ══════════════════════════════════════════════════════════
# API steps  (use the `api` + `api_ai` fixtures from conftest)
# ══════════════════════════════════════════════════════════
@given(parsers.parse('the API base url is "{url}"'))
def _api_base(api, url: str) -> None:
    api.base_url = url


@when(parsers.parse('I send a {method} request to "{path}"'))
def _send_request(api, ctx, method: str, path: str) -> None:
    ctx["response"] = api.request(method.upper(), path)


@when(parsers.parse('I POST "{path}" with a fake user'))
def _post_fake_user(api, ctx, path: str) -> None:
    from omnitest.models import User

    ctx["payload"] = User.fake().model_dump(exclude_none=True)
    ctx["response"] = api.post(path, json=ctx["payload"])


@then(parsers.parse("the response status should be {code:d}"))
def _assert_status(ctx, code: int) -> None:
    ctx["response"].expect_status(code)


@then(parsers.parse('the response body should have "{path}"'))
def _assert_path(ctx, path: str) -> None:
    ctx["response"].expect_path(path)


@then("the response should be semantically valid")
def _assert_semantic(ctx, api_ai) -> None:
    verdict = api_ai.assess(ctx["response"])
    assert verdict.get("pass"), f"AI flagged the response: {verdict.get('reason')}"


# ══════════════════════════════════════════════════════════
# UI steps  (use the self-healing `ai_page` fixture)
# ══════════════════════════════════════════════════════════
@given(parsers.parse('I open "{url}"'))
def _open(ai_page, url: str) -> None:
    ai_page.page.goto(url)


@when(parsers.parse('I click "{intent}"'))
def _click(ai_page, intent: str) -> None:
    # `intent` doubles as the human description the AI uses to self-heal.
    ai_page.click(intent, intent=intent)


@when(parsers.parse('I fill "{intent}" with "{value}"'))
def _fill(ai_page, intent: str, value: str) -> None:
    ai_page.fill(intent, value, intent=intent)


@then(parsers.parse('I should see "{text}"'))
def _see_text(ai_page, text: str) -> None:
    assert text in ai_page.page.content(), f"'{text}' not found on page"


# ══════════════════════════════════════════════════════════
# Email steps  (use `email` + `email_ai` fixtures)
# ══════════════════════════════════════════════════════════
@when(parsers.parse('I send an email to "{to}" with subject "{subject}"'))
def _send_email(email, ctx, to: str, subject: str) -> None:
    email.send(EmailMessage(to=to, subject=subject, body=ctx.get("body", "test body")))
    ctx["subject"] = subject


@when(parsers.parse('I wait for an email with subject "{subject}"'))
def _wait_email(email, ctx, subject: str) -> None:
    ctx["received"] = email.wait_for(subject=subject)


@then(parsers.parse('the email should convey "{expectation}"'))
def _verify_email(email, ctx, expectation: str) -> None:
    verdict = email.verify_content(ctx["received"], expectation)
    assert verdict.get("pass"), f"AI flagged the email: {verdict.get('reason')}"
