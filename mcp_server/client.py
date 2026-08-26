"""Async HTTP client for the Merrick memory daemon API.

Talks to Merrick over HTTP — no direct DB access. This keeps the MCP
server clean, stateless, and capable of connecting to remote instances.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import MERRICK_API_KEY, MERRICK_URL

logger = logging.getLogger("merrick.mcp")


class MerrickClient:
    """Async HTTP client for Merrick's REST API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self._base_url = (base_url or MERRICK_URL).rstrip("/")
        self._api_key = api_key or MERRICK_API_KEY
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Create the underlying HTTP client."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
        )
        logger.info("Merrick client started → %s", self._base_url)

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._http:
            await self._http.aclose()
            self._http = None
            logger.info("Merrick client stopped")

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("MerrickClient not started — call start() first")
        return self._http

    # ── Memory operations ────────────────────────────────────────────

    async def write_memory(
        self,
        content: str,
        source: str = "mcp",
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Write a memory to Merrick (via mem0 + Honcho)."""
        payload: dict[str, Any] = {
            "content": content,
            "source": source,
        }
        resp = await self._client().post("/api/memory/write", json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Merrick returns {status, results: {mem0: {success, id}, honcho: {success, id}}}
        # Extract a clean ID from whichever store succeeded
        mem0_result = data.get("results", {}).get("mem0", {})
        memory_id = mem0_result.get("id", "")

        # If categories were requested, assign them via the categories API
        if categories and memory_id:
            await self._assign_categories(memory_id, categories)

        return {
            "success": data.get("status") in ("ok", "partial"),
            "memory_id": memory_id,
            "status": data.get("status", "unknown"),
        }

    async def _assign_categories(self, memory_id: str, categories: list[str]) -> None:
        """Assign a memory to categories, creating categories if needed."""
        client = self._client()
        for cat_name in categories:
            try:
                # Get or create category
                existing = await client.get("/api/categories")
                existing.raise_for_status()
                cats = existing.json().get("categories", [])
                cat_id = None
                for c in cats:
                    if c.get("name") == cat_name:
                        cat_id = c.get("id")
                        break

                if not cat_id:
                    create_resp = await client.post(
                        "/api/categories",
                        json={"name": cat_name},
                    )
                    if create_resp.status_code == 200:
                        cat_id = create_resp.json().get("id")

                if cat_id:
                    await client.post(
                        f"/api/categories/{cat_id}/assign",
                        json={"memory_id": memory_id},
                    )
            except Exception as exc:
                logger.warning("Failed to assign category %s: %s", cat_name, exc)

    async def search_memories(
        self,
        query: str,
        categories: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memories by query across mem0 + Honcho."""
        payload: dict[str, Any] = {"query": query}
        resp = await self._client().post("/api/query", json=payload)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])

        # Apply category filter client-side if requested
        if categories:
            results = [
                r for r in results
                if any(
                    cat in categories
                    for cat in (r.get("metadata", {}).get("categories") or [])
                )
            ]

        return results[:limit]

    async def list_memories(
        self,
        limit: int = 20,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """List recent memories. Uses the export endpoint since there's
        no dedicated list endpoint in Merrick's HTTP API.
        """
        params: dict[str, str] = {}
        if category:
            # We need the category ID, not name. Fetch categories first.
            cat_id = await self._get_category_id(category)
            if cat_id:
                params["category_id"] = cat_id

        resp = await self._client().get("/api/export/json", params=params)
        resp.raise_for_status()
        data = resp.json()

        memories = data.get("memories", [])
        return memories[:limit]

    async def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        """Get a specific memory by ID.

        Merrick has no GET /api/memory/{id} endpoint, so we fetch all
        memories via the export endpoint and filter. For large stores
        this is suboptimal — a dedicated endpoint would be better.
        """
        resp = await self._client().get("/api/export/json")
        resp.raise_for_status()
        data = resp.json()

        for mem in data.get("memories", []):
            if mem.get("id") == memory_id:
                return mem
        return None

    async def delete_memory(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by ID.

        Merrick does not expose a DELETE endpoint over HTTP. This
        always returns an error — the operation requires direct DB
        access or a new Merrick endpoint.
        """
        return {
            "success": False,
            "error": (
                "Merrick does not expose a delete endpoint over HTTP. "
                "Memory deletion requires direct database access or a "
                "new Merrick API endpoint (POST /api/memory/delete)."
            ),
        }

    async def get_status(self) -> dict[str, Any]:
        """Get Merrick health status."""
        resp = await self._client().get("/api/status")
        resp.raise_for_status()
        return resp.json()

    # ── Helpers ──────────────────────────────────────────────────────

    async def _get_category_id(self, name: str) -> str | None:
        """Look up a category ID by name."""
        try:
            resp = await self._client().get("/api/categories")
            resp.raise_for_status()
            for cat in resp.json().get("categories", []):
                if cat.get("name") == name:
                    return cat.get("id")
        except Exception as exc:
            logger.warning("Failed to look up category %s: %s", name, exc)
        return None
