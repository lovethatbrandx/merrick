"""Merrick MCP Server

Exposes Merrick's memory system as MCP tools and resources for any
MCP-compatible client (LM Studio, Claude Desktop, VS Code, etc.).

Tools:  write_memory, search_memories, list_memories, get_memory,
        delete_memory, get_status
Resources: merrick://status, merrick://memories

Run with:
    python -m mcp_server          # stdio transport (default)
    mcp run mcp_server/server.py  # via MCP CLI
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from .client import MerrickClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("merrick.mcp")


# ── Lifespan context ────────────────────────────────────────────────


@dataclass
class AppContext:
    """Shared state available to every tool handler."""

    client: MerrickClient


# Module-level client reference for resource handlers (which can't
# receive Context on static URIs).
_client: MerrickClient | None = None


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    """Start the Merrick HTTP client on server startup, tear it down on exit."""
    global _client
    client = MerrickClient()
    await client.start()
    _client = client
    try:
        yield AppContext(client=client)
    finally:
        _client = None
        await client.stop()


def _get_client() -> MerrickClient:
    """Get the active client (for resource handlers that can't use Context)."""
    if _client is None:
        raise RuntimeError("Merrick client not initialized — server may not be running")
    return _client


# ── MCP Server ──────────────────────────────────────────────────────

mcp = MCPServer("Merrick", lifespan=app_lifespan)


# ── Tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def write_memory(
    content: Annotated[str, Field(description="The memory content to store.")],
    source: Annotated[str, Field(description="Source identifier for this memory.")] = "mcp",
    categories: Annotated[
        list[str] | None,
        Field(description="Optional list of category names to assign."),
    ] = None,
    ctx: Context[AppContext] = None,
) -> str:
    """Write a memory to Merrick. Stores in both mem0 and Honcho.

    Returns the memory ID and write status.
    """
    client = ctx.request_context.lifespan_context.client
    try:
        result = await client.write_memory(content=content, source=source, categories=categories)
        return json.dumps(result, indent=2)
    except Exception as exc:
        raise RuntimeError(f"Failed to write memory: {exc}") from exc


@mcp.tool()
async def search_memories(
    query: Annotated[str, Field(description="Search query to find matching memories.")],
    categories: Annotated[
        list[str] | None,
        Field(description="Optional category names to filter results."),
    ] = None,
    limit: Annotated[int, Field(description="Maximum results to return.", ge=1, le=100)] = 10,
    ctx: Context[AppContext] = None,
) -> str:
    """Search memories by query across mem0 and Honcho.

    Returns matching memories with content, source, and metadata.
    """
    client = ctx.request_context.lifespan_context.client
    try:
        results = await client.search_memories(query=query, categories=categories, limit=limit)
        return json.dumps({"results": results, "count": len(results)}, indent=2)
    except Exception as exc:
        raise RuntimeError(f"Failed to search memories: {exc}") from exc


@mcp.tool()
async def list_memories(
    limit: Annotated[int, Field(description="Maximum memories to return.", ge=1, le=200)] = 20,
    category: Annotated[str | None, Field(description="Optional category name to filter by.")] = None,
    ctx: Context[AppContext] = None,
) -> str:
    """List recent memories, optionally filtered by category.

    Returns memories with id, content, source, and categories.
    """
    client = ctx.request_context.lifespan_context.client
    try:
        results = await client.list_memories(limit=limit, category=category)
        return json.dumps({"memories": results, "count": len(results)}, indent=2)
    except Exception as exc:
        raise RuntimeError(f"Failed to list memories: {exc}") from exc


@mcp.tool()
async def get_memory(
    memory_id: Annotated[str, Field(description="The memory ID to retrieve.")],
    ctx: Context[AppContext] = None,
) -> str:
    """Get a specific memory by its ID.

    Note: Merrick has no per-memory GET endpoint, so this fetches all
    memories and filters. For large stores this may be slow.
    """
    client = ctx.request_context.lifespan_context.client
    try:
        memory = await client.get_memory(memory_id)
        if memory is None:
            return json.dumps({"error": f"Memory not found: {memory_id}"})
        return json.dumps(memory, indent=2)
    except Exception as exc:
        raise RuntimeError(f"Failed to get memory: {exc}") from exc


@mcp.tool()
async def delete_memory(
    memory_id: Annotated[str, Field(description="The memory ID to delete.")],
    ctx: Context[AppContext] = None,
) -> str:
    """Delete a memory by ID.

    Currently unsupported — Merrick does not expose a delete endpoint
    over HTTP. Returns an error with guidance.
    """
    client = ctx.request_context.lifespan_context.client
    result = await client.delete_memory(memory_id)
    return json.dumps(result, indent=2)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
async def get_status(ctx: Context[AppContext] = None) -> str:
    """Get Merrick health status.

    Returns counts, session info, sync status, and recent samples
    from both mem0 and Honcho stores.
    """
    client = ctx.request_context.lifespan_context.client
    try:
        status = await client.get_status()
        return json.dumps(status, indent=2, default=str)
    except Exception as exc:
        raise RuntimeError(f"Failed to get status: {exc}") from exc


# ── Resources ───────────────────────────────────────────────────────
# Static resources can't receive Context, so these use the module-level
# _client reference set by the lifespan.


@mcp.resource("merrick://status", mime_type="application/json")
async def status_resource() -> str:
    """Merrick health status as a readable resource.

    Same data as the get_status tool, but exposed as a resource
    that the application can load as context.
    """
    try:
        client = _get_client()
        status = await client.get_status()
        return json.dumps(status, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("merrick://memories", mime_type="application/json")
async def memories_resource() -> str:
    """Recent memories as a readable resource.

    Returns the 20 most recent memories. The application can load
    this as context for the model.
    """
    try:
        client = _get_client()
        memories = await client.list_memories(limit=20)
        return json.dumps({"memories": memories, "count": len(memories)}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    asyncio.run(mcp.run_stdio_async())
