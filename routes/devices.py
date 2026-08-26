from fastapi import APIRouter

import provisioning
from config import logger

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def list_devices():
    """List all provisioned devices (dashboard only)."""
    try:
        devices = provisioning.list_devices()
        return {"devices": devices, "count": len(devices)}
    except Exception as e:
        logger.error("list devices failed: %s", e)
        return {"devices": [], "count": 0, "error": str(e)}
