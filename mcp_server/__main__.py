"""Entry point for `python -m mcp_server`.

Starts the MCP server on stdio transport, which is the primary
target for LM Studio and similar local MCP hosts.
"""

import asyncio

from .server import mcp


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
