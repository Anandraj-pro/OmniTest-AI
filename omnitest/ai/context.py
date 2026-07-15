"""Ambient story context so AI calls can be attributed to a user story.

Set the current story (usually via the `story` pytest marker — see tests/conftest.py),
and every AI call made while it's active is tagged with that story ID in the prompt
tracker. The director dashboard then rolls cost/usage up by story.

    from omnitest.ai.context import story
    with story("OMNI-142"):
        agent.verify(...)     # logged with tags={"story": "OMNI-142"}
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator

_current_story: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_story", default=None
)


def set_story(story_id: str | None) -> None:
    _current_story.set(story_id)


def get_story() -> str | None:
    return _current_story.get()


@contextlib.contextmanager
def story(story_id: str) -> Iterator[None]:
    """Scope a block of AI calls to a story ID (auto-resets afterward)."""
    token = _current_story.set(story_id)
    try:
        yield
    finally:
        _current_story.reset(token)
