"""Configuration for the Merrick MCP server.

Reads from environment variables. All settings have sensible defaults
for a local Merrick installation.
"""

import os


MERRICK_URL: str = os.getenv("MERRICK_URL", "http://localhost:5001")
MERRICK_API_KEY: str = os.getenv("MERRICK_API_KEY", "")
