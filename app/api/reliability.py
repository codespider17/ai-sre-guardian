from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.changes import DatabaseSession, IngestAuthorization
from app.schemas_slo import (
    SLOEvaluationCreate,
    SLOEvaluationReceipt,
    SLOPolicyCreate,
    SLOPolicyReceipt,
)
from app.services.reliability_evaluation import (
    ReliabilityServiceNotFoundError,
    SLOPolicyConflictError,
    SLOPolicyNotFoundError,
    create_slo_policy,
    evaluate_and_persist_slo,
)

router = APIRouter(
    prefix="/api/v1/reliability",
    tags=["reliability"],
)


@router.post(
    "/policies",
    response_model=SLOPolicyReceipt,
    status_code=status.HTTP_201_CREATED,
)
def create_policy(
    request: SLOPolicyCreate,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> SLOPolicyReceipt:
    try:
        return create_slo_policy(session, request)
    except ReliabilityServiceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="service was not found",
        ) from exc
    except SLOPolicyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLO policy name has a different definition",
        ) from exc


@router.post(
    "/policies/{policy_id}/evaluations",
    response_model=SLOEvaluationReceipt,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_policy(
    policy_id: UUID,
    request: SLOEvaluationCreate,
    session: DatabaseSession,
    _authorization: IngestAuthorization,
) -> SLOEvaluationReceipt:
    try:
        return evaluate_and_persist_slo(
            session,
            policy_id,
            request,
        )
    except SLOPolicyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SLO policy was not found",
        ) from exc
