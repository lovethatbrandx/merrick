"""Configuration for the Merrick CLI."""

import os

# Merrick API base URL
MERRICK_URL = os.getenv("MERRICK_URL", "http://localhost:5001")

# Request timeout in seconds
REQUEST_TIMEOUT = int(os.getenv("MERRICK_CLI_TIMEOUT", "30"))
