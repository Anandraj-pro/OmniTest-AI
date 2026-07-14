"""httpx-based API testing client with schema + AI-assisted assertions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import validate as _jsonschema_validate

from omnitest.config import settings
from omnitest.utils.logger import get_logger

log = get_logger("api")


@dataclass(slots=True)
class ApiResponse:
    status: int
    headers: dict[str, str]
    body: Any
    elapsed_ms: int
    raw: httpx.Response

    @property
    def text(self) -> str:
        return self.raw.text

    def json_str(self) -> str:
        try:
            return json.dumps(self.body, ensure_ascii=False, indent=2)
        except TypeError:
            return self.text

    # ── fluent assertions ───────────────────────────────
    def expect_status(self, code: int) -> "ApiResponse":
        assert self.status == code, f"expected {code}, got {self.status}: {self.text[:300]}"
        return self

    def expect_schema(self, schema: dict[str, Any]) -> "ApiResponse":
        _jsonschema_validate(instance=self.body, schema=schema)
        return self

    def expect_path(self, dotted: str, value: Any) -> "ApiResponse":
        cur: Any = self.body
        for part in dotted.split("."):
            cur = cur[int(part)] if part.isdigit() else cur[part]
        assert cur == value, f"{dotted}: expected {value!r}, got {cur!r}"
        return self


class ApiClient:
    def __init__(self, base_url: str | None = None, **kw: Any) -> None:
        self._client = httpx.Client(
            base_url=base_url or settings.api_base_url,
            timeout=kw.pop("timeout", 30.0),
            **kw,
        )

    def request(self, method: str, url: str, **kw: Any) -> ApiResponse:
        r = self._client.request(method, url, **kw)
        try:
            body: Any = r.json()
        except (json.JSONDecodeError, ValueError):
            body = r.text
        log.info("%s %s -> %s (%dms)", method.upper(), url, r.status_code,
                 int(r.elapsed.total_seconds() * 1000))
        return ApiResponse(
            status=r.status_code,
            headers=dict(r.headers),
            body=body,
            elapsed_ms=int(r.elapsed.total_seconds() * 1000),
            raw=r,
        )

    def get(self, url: str, **kw: Any) -> ApiResponse:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> ApiResponse:
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw: Any) -> ApiResponse:
        return self.request("PUT", url, **kw)

    def delete(self, url: str, **kw: Any) -> ApiResponse:
        return self.request("DELETE", url, **kw)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()