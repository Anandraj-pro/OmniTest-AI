"""Self-contained smoke tests — no network, no browser, no external services.

These give CI a fast, always-runnable green signal (and prove the framework
imports and wires correctly). The API/UI/email suites need a real app-under-test
and are gated separately.
"""
from __future__ import annotations

import pytest

from omnitest.ai.tcro import TCRO
from omnitest.ai.client import AIClient, Tier
from omnitest.ai.context import story, get_story
from omnitest.ai.tracker import _cost
from omnitest.reporting.director_dashboard import build_director_dashboard

pytestmark = pytest.mark.smoke


def test_tcro_renders_both_halves():
    t = TCRO(task="do x", context="ctx", rules=["r1"], output="json")
    assert "do x" in t.user_text() and "json" in t.user_text()
    assert "ctx" in t.system_text() and "r1" in t.system_text()


def test_tcro_requires_a_task():
    with pytest.raises(ValueError):
        TCRO(task="")


def test_model_routing_has_three_tiers():
    client = AIClient.shared()
    models = {tier: client.model_for(tier) for tier in Tier}
    assert len(models) == 3 and all(models.values())


def test_local_provider_is_free_but_claude_is_not():
    usage = {"input_tokens": 1000, "output_tokens": 500}
    assert _cost("qwen2.5:7b", usage, "ollama") == 0.0
    assert _cost("claude-opus-4-8", usage, "anthropic") > 0.0


def test_story_context_sets_and_clears():
    assert get_story() is None
    with story("OMNI-1"):
        assert get_story() == "OMNI-1"
    assert get_story() is None


def test_director_dashboard_builds(tmp_path):
    out = build_director_dashboard(tmp_path / "director.html")
    assert out.exists() and "QA Director" in out.read_text()
