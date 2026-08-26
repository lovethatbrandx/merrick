import time
import hashlib
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import database as db
from config import logger

# ---------------------------------------------------------------------------
# In-memory rate limiter: {key_id: [timestamp, ...]}
# Good enough for a local daemon. No Redis needed.
# ---------------------------------------------------------------------------
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_WINDOW = 60  # seconds


def _check_rate_limit(key_id: str, rate_limit: int) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    window_start = now - RATE_WINDOW
    timestamps = _rate_limits[key_id]
    # Prune timestamps outside the window
    _rate_limits[key_id] = [t for t in timestamps if t > window_start]
    if len(_rate_limits[key_id]) >= rate_limit:
        return False
    _rate_limits[key_id].append(now)
    return True


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Intercepts every /v1/* request and enforces key-first auth:
      1. Extract Bearer token from Authorization header
      2. SHA-256 hash → lookup in api_keys table
      3. Rate-limit check (in-memory sliding window)
      4. Permission check for write methods
      5. Inject full scope into request.state
      6. Update last_used_at
    """

    async def dispatch(self, request: Request, call_next):
        # Only intercept /v1/* — internal /api/* routes bypass auth
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        # ── 1. Extract Bearer token ───────────────────────────────────
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"},
            )

        token = auth_header[7:]  # strip "Bearer "

        # ── 2. Validate format and hash ───────────────────────────────
        if not token.startswith("merrick_sk_"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid key format"},
            )

        key_hash = hashlib.sha256(token.encode()).hexdigest()

        # ── 3. DB lookup ──────────────────────────────────────────────
        try:
            row = db.query_one(
                "SELECT * FROM api_keys WHERE key_hash = %s AND active = true",
                (key_hash,),
            )
        except Exception as e:
            logger.error("Auth DB lookup failed: %s", e)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal auth error"},
            )

        if not row:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or inactive API key"},
            )

        key = dict(row)
        key_id = str(key["id"])

        # ── 4. Rate limit ─────────────────────────────────────────────
        if not _check_rate_limit(key_id, key.get("rate_limit", 100)):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": 60},
            )

        # ── 5. Permission check for mutating methods ──────────────────
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            permissions = key.get("permissions") or []
            if "write" not in permissions:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Write permission required for this key"},
                )

        # ── 6. Inject scope into request.state ────────────────────────
        request.state.key_id = key_id
        request.state.key_name = key["key_name"]
        request.state.device_id = key["device_id"]
        request.state.agent_slug = key.get("agent_slug")
        request.state.load_memories = key.get("load_memories", True)
        request.state.memory_categories = key.get("memory_categories")
        request.state.memory_exclude_categories = key.get("memory_exclude_categories") or []
        request.state.memory_scope = key.get("memory_scope", "shared")
        request.state.max_memory_tokens = key.get("max_memory_tokens", 2000)
        request.state.permissions = key.get("permissions") or []

        # ── 7. Update last_used_at (fire-and-forget, success only) ────
        # Only reached after rate limit AND permission checks both passed.
        try:
            db.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s::uuid",
                (key_id,),
            )
        except Exception as e:
            logger.warning("Failed to update last_used_at for key %s: %s", key_id, e)

        return await call_next(request)
