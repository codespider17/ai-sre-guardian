import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas_change import ChangeEvaluationReceipt, ChangeEvaluationRequest
from app.services.change_ingestion import (
    ServiceNotRegisteredError,
    evaluate_and_persist_change,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/changes", tags=["changes"])
bearer = HTTPBearer(auto_error=False)
DatabaseSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer),
]


def require_ingest_token(credentials: BearerCredentials) -> None:
    expected_token = get_settings().ingest_token
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid ingestion token",
            headers={"WWW-Authenticate": "Bearer"},
        )


IngestAuthorization = Annotated[None, Depends(require_ingest_token)]


@router.post("/evaluate", response_model=ChangeEvaluationReceipt)
def evaluate_change(
    request: ChangeEvaluationRequest,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> ChangeEvaluationReceipt:
    try:
        return evaluate_and_persist_change(session, request)
    except ServiceNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository is not registered",
        ) from exc
