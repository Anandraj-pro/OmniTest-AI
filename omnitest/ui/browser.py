"""Playwright lifecycle manager (sync API)."""
from __future__ import annotations

from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from omnitest.config import settings


class BrowserManager:
    def __init__(self, *, headless: bool = True, browser: str = "chromium") -> None:
        self._headless = headless
        self._browser_name = browser
        self._pw: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def start(self) -> Page:
        self._pw = sync_playwright().start()
        launcher = getattr(self._pw, self._browser_name)
        self._browser = launcher.launch(headless=self._headless)
        self._context = self._browser.new_context(base_url=settings.base_url)
        # Trace for Allure attachments on failure.
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        return self._context.new_page()

    @property
    def context(self) -> BrowserContext:
        assert self._context is not None, "call start() first"
        return self._context

    def stop(self, trace_path: str | None = None) -> None:
        if self._context is not None:
            try:
                self._context.tracing.stop(path=trace_path)
            except Exception:  # pragma: no cover
                pass
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()

    def __enter__(self) -> Page:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()