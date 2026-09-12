from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.changes import DatabaseSession, IngestAuthorization
from app.schemas_governance import (
    HumanApprovalCreate,
    HumanApprovalReceipt,
    ReleaseRecommendationCreate,
    ReleaseRecommendationReceipt,
)
from app.services.release_governance import (
    ReleaseGovernanceConflictError,
    ReleaseObservationNotFoundError,
    ReleaseRecommendationNotFoundError,
    record_human_approval,
    record_release_recommendation,
)

router = APIRouter(
    prefix="/api/v1/release-governance",
    tags=["release-governance"],
)


@router.post(
    "/recommendations",
    response_model=ReleaseRecommendationReceipt,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation(
    request: ReleaseRecommendationCreate,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> ReleaseRecommendationReceipt:
    try:
        return record_release_recommendation(session, request)
    except ReleaseObservationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="release observation was not found",
        ) from exc
    except ReleaseGovernanceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/recommendations/{recommendation_id}/decisions",
    response_model=HumanApprovalReceipt,
    status_code=status.HTTP_201_CREATED,
)
def create_human_decision(
    recommendation_id: UUID,
    request: HumanApprovalCreate,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> HumanApprovalReceipt:
    try:
        return record_human_approval(
            session,
            recommendation_id,
            request,
        )
    except ReleaseRecommendationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="release recommendation was not found",
        ) from exc
    except ReleaseGovernanceConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
