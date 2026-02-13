import logging

from fastapi import FastAPI

from app.api.routes import router
from app.db.init_db import init_db

logger = logging.getLogger(__name__)

app = FastAPI(title="BidExpert API", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database init skipped: %s", exc)
