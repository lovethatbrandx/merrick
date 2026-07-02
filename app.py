import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
import database as db
import sync
from routes.sync import router as sync_router
from routes.query import router as query_router
from routes.status import router as status_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("merrick")


def _sync_loop():
    while True:
        time.sleep(config.SYNC_INTERVAL)
        try:
            result = sync.run_full_sync()
            logger.info("Background sync finished: %s", result)
        except Exception as e:
            logger.error("Background sync error: %s", e)


@asynccontextmanager
async def lifespan(app_instance):
    # Startup
    try:
        db.init_schema()
    except Exception as e:
        logger.error("Schema init failed: %s", e)

    if config.SYNC_ENABLED:
        t = threading.Thread(target=_sync_loop, daemon=True)
        t.start()
        logger.info("Background sync started (interval=%ds)", config.SYNC_INTERVAL)

    yield

    # Shutdown (nothing to clean up)


app = FastAPI(title="Merrick", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sync_router)
app.include_router(query_router)
app.include_router(status_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "merrick"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5001, log_level="info")
