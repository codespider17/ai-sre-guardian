from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.changes import router as changes_router
from app.api.devflow_integration import router as devflow_integration_router
from app.api.release_governance import router as release_governance_router
from app.api.reliability import router as reliability_router
from app.database import get_db
from app.settings import get_settings

settings = get_settings()
app = FastAPI(title="AI-SRE Guardian", version=settings.version)
DatabaseSession = Annotated[Session, Depends(get_db)]
app.include_router(changes_router)
app.include_router(reliability_router)
app.include_router(devflow_integration_router)


app.include_router(release_governance_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.version,
    }


@app.get("/ready", tags=["system"])
def ready(db: DatabaseSession) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "service": settings.service_name,
        "database": "ok",
    }
