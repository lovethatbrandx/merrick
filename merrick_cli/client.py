"""HTTP client for the Merrick API."""

from typing import Any

import httpx

from merrick_cli.config import MERRICK_URL, REQUEST_TIMEOUT


class MerrickClient:
    """Thin wrapper around httpx for talking to the Merrick API."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or MERRICK_URL).rstrip("/")
        self.timeout = timeout or REQUEST_TIMEOUT

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str, **kwargs) -> dict[str, Any]:
        resp = httpx.get(self._url(path), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict | None = None, **kwargs) -> dict[str, Any]:
        resp = httpx.post(self._url(path), json=json, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ── Health ──────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return self._get("/api/health")

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return self._get("/api/status")

    # ── Devices ─────────────────────────────────────────────────────

    def list_devices(self) -> dict[str, Any]:
        return self._get("/api/devices")

    # ── Keys ────────────────────────────────────────────────────────

    def list_keys(self) -> dict[str, Any]:
        return self._get("/api/keys")

    def create_key(
        self,
        device_id: str,
        key_name: str,
        agent_slug: str | None = None,
        permissions: list[str] | None = None,
        memory_scope: str = "shared",
        max_memory_tokens: int = 2000,
        rate_limit: int = 100,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "device_id": device_id,
            "key_name": key_name,
            "permissions": permissions or ["read", "write"],
            "memory_scope": memory_scope,
            "max_memory_tokens": max_memory_tokens,
            "rate_limit": rate_limit,
        }
        if agent_slug:
            payload["agent_slug"] = agent_slug
        return self._post("/api/keys", json=payload)

    # ── Memory ──────────────────────────────────────────────────────

    def write_memory(
        self,
        content: str,
        source: str = "cli",
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content, "source": source}
        if user_id:
            payload["user_id"] = user_id
        if metadata:
            payload["metadata"] = metadata
        return self._post("/api/memory/write", json=payload)

    def query_memories(self, query: str) -> dict[str, Any]:
        return self._post("/api/query", json={"query": query})

    # ── Export ──────────────────────────────────────────────────────

    def export_json(self, category_id: str | None = None) -> dict[str, Any]:
        params = {}
        if category_id:
            params["category_id"] = category_id
        return self._get("/api/export/json", params=params)

    # ── Sync ────────────────────────────────────────────────────────

    def trigger_sync(self) -> dict[str, Any]:
        return self._post("/api/sync/trigger")

    def sync_status(self) -> dict[str, Any]:
        return self._get("/api/sync/status")

    def sync_log(self, limit: int = 50) -> dict[str, Any]:
        return self._get("/api/sync/log", params={"limit": limit})
