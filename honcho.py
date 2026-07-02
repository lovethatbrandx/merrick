import httpx
import logging
from config import HONCHO_URL, HONCHO_WORKSPACE, HONCHO_USER_PEER

logger = logging.getLogger("merrick.honcho")

_client = None


def get_client():
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(base_url=HONCHO_URL, timeout=30.0)
    return _client


def create_session(session_id: str, title: str = "Merrick Import") -> dict:
    client = get_client()
    resp = client.post(
        f"/v3/workspaces/{HONCHO_WORKSPACE}/sessions",
        json={"id": session_id, "title": title},
    )
    resp.raise_for_status()
    return resp.json()


def post_message(session_id: str, peer: str, content: str) -> dict:
    client = get_client()
    resp = client.post(
        f"/v3/workspaces/{HONCHO_WORKSPACE}/sessions/{session_id}/messages",
        json={"messages": [{"peer_id": HONCHO_USER_PEER, "content": content}]},
    )
    resp.raise_for_status()
    data = resp.json()
    # Honcho returns a list of created messages
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data


def list_conclusions(limit: int = 100) -> list:
    client = get_client()
    resp = client.post(
        f"/v3/workspaces/{HONCHO_WORKSPACE}/conclusions/list",
        json={"limit": limit},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    # Honcho returns {"items": [...], "total": N, ...}
    return data.get("items", data.get("conclusions", []))


def search_peers(peer_id: str, query: str) -> list:
    client = get_client()
    resp = client.post(
        f"/v3/workspaces/{HONCHO_WORKSPACE}/peers/{peer_id}/search",
        json={"query": query},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("results", [])


def list_sessions() -> list:
    client = get_client()
    resp = client.post(
        f"/v3/workspaces/{HONCHO_WORKSPACE}/sessions/list",
        json={},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    # Honcho returns {"items": [...], "total": N, ...}
    return data.get("items", data.get("sessions", []))
