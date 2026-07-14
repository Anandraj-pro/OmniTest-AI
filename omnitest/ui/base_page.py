"""Page-object base with AI self-healing selectors.

When a selector stops matching, FailureAnalystAgent inspects the live DOM and
proposes a resilient replacement, so a UI tweak doesn't immediately red-fail the
suite. Heals are logged (via the prompt tracker) for review.
"""
from __future__ import annotations

from playwright.sync_api import Locator, Page, TimeoutError as PWTimeout

from omnitest.ai.agents import FailureAnalystAgent
from omnitest.utils.logger import get_logger

log = get_logger("ui")


class BasePage:
    def __init__(self, page: Page, *, self_heal: bool = True) -> None:
        self.page = page
        self._heal = self_heal
        self._healer = FailureAnalystAgent() if self_heal else None

    def locate(self, selector: str, *, intent: str, timeout: int = 5000) -> Locator:
        """Return a locator, healing the selector via AI if it doesn't resolve."""
        loc = self.page.locator(selector)
        try:
            loc.wait_for(state="attached", timeout=timeout)
            return loc
        except PWTimeout:
            if not (self._heal and self._healer):
                raise
            log.warning("selector miss %r — attempting AI self-heal", selector)
            dom = self.page.content()
            fix = self._healer.heal_selector(broken=selector, dom_snippet=dom, intent=intent)
            healed = fix.get("selector", "")
            log.info("healed %r -> %r (%s)", selector, healed, fix.get("strategy"))
            new = self.page.locator(healed)
            new.wait_for(state="attached", timeout=timeout)
            return new

    def click(self, selector: str, *, intent: str) -> None:
        self.locate(selector, intent=intent).click()

    def fill(self, selector: str, value: str, *, intent: str) -> None:
        self.locate(selector, intent=intent).fill(value)

    def text(self, selector: str, *, intent: str) -> str:
        return self.locate(selector, intent=intent).inner_text()