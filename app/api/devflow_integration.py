from fastapi import APIRouter, HTTPException, status

from app.api.changes import DatabaseSession, IngestAuthorization
from app.schemas_devflow import (
    DevFlowReleaseObservationCreate,
    DevFlowReleaseObservationReceipt,
)
from app.services.devflow_integration import (
    IntegrationServiceNotFoundError,
    ReleaseObservationConflictError,
    record_devflow_release,
)

router = APIRouter(
    prefix="/api/v1/integrations/devflow",
    tags=["devflow-integration"],
)


@router.post(
    "/releases",
    response_model=DevFlowReleaseObservationReceipt,
    status_code=status.HTTP_201_CREATED,
)
def observe_release(
    request: DevFlowReleaseObservationCreate,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> DevFlowReleaseObservationReceipt:
    try:
        return record_devflow_release(session, request)
    except IntegrationServiceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="service was not found",
        ) from exc
    except ReleaseObservationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="delivery ID has a different payload",
        ) from exc
