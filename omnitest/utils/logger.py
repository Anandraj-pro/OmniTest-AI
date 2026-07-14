"""Rich-backed logger with a plain fallback."""
from __future__ import annotations

import logging

try:
    from rich.logging import RichHandler
    _HANDLER: logging.Handler = RichHandler(rich_tracebacks=True, show_path=False)
    _FMT = "%(message)s"
except Exception:  # pragma: no cover - rich optional
    _HANDLER = logging.StreamHandler()
    _FMT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    _HANDLER.setFormatter(logging.Formatter(_FMT, datefmt="%H:%M:%S"))
    root = logging.getLogger("omnitest")
    root.setLevel(logging.INFO)
    root.addHandler(_HANDLER)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"omnitest.{name}")