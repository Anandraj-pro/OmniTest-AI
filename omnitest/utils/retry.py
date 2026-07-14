"""Thin wrapper over tenacity for polling flows (e.g. waiting for an email)."""
from __future__ import annotations

from typing import Callable, TypeVar

from tenacity import retry as _retry
from tenacity import stop_after_delay, wait_fixed, retry_if_exception_type

T = TypeVar("T")


def retry(
    *,
    timeout: float = 60.0,
    interval: float = 3.0,
    on: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Retry a callable until it stops raising `on`, up to `timeout` seconds."""
    return _retry(
        stop=stop_after_delay(timeout),
        wait=wait_fixed(interval),
        retry=retry_if_exception_type(on),
        reraise=True,
    )