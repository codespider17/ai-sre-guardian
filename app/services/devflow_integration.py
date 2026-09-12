from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ReleaseObservation, Service
from app.schemas_devflow import (
    DevFlowReleaseObservationCreate,
    DevFlowReleaseObservationReceipt,
    DevFlowReleaseStatus,
)


class IntegrationServiceNotFoundError(Exception):
    pass


class ReleaseObservationConflictError(Exception):
    pass


def observation_receipt(
    observation: ReleaseObservation,
    status: str,
) -> DevFlowReleaseObservationReceipt:
    return DevFlowReleaseObservationReceipt(
        status=status,
        observation_id=observation.id,
        delivery_id=observation.delivery_id,
        service_id=observation.service_id,
        pipeline_run_id=observation.source_pipeline_run_id,
        deployment_id=observation.source_deployment_id,
        release_status=DevFlowReleaseStatus(observation.status),
        observed_at=observation.observed_at,
    )


def record_devflow_release(
    session: Session,
    request: DevFlowReleaseObservationCreate,
) -> DevFlowReleaseObservationReceipt:
    service = session.get(Service, request.service_id)
    if service is None:
        raise IntegrationServiceNotFoundError(str(request.service_id))

    payload = request.model_dump(mode="json")
    existing = session.scalar(
        select(ReleaseObservation).where(
            ReleaseObservation.delivery_id == request.delivery_id
        )
    )
    if existing is not None:
        if existing.raw_event != payload:
            raise ReleaseObservationConflictError(request.delivery_id)
        return observation_receipt(existing, "duplicate")

    observation = ReleaseObservation(
        service_id=request.service_id,
        delivery_id=request.delivery_id,
        source="devflow",
        source_pipeline_run_id=request.pipeline_run_id,
        source_deployment_id=request.deployment_id,
        environment=request.environment,
        commit_sha=request.commit_sha,
        image_reference=request.image_reference,
        status=request.status.value,
        raw_event=payload,
        observed_at=request.observed_at,
    )
    session.add(observation)
    session.flush()
    session.add(
        AuditEvent(
            entity_type="release_observation",
            entity_id=observation.id,
            action="devflow.release_observed",
            actor="devflow-integration",
            details={
                "delivery_id": request.delivery_id,
                "pipeline_run_id": str(request.pipeline_run_id),
                "deployment_id": (
                    str(request.deployment_id)
                    if request.deployment_id is not None
                    else None
                ),
                "status": request.status.value,
            },
        )
    )
    session.commit()
    session.refresh(observation)
    return observation_receipt(observation, "recorded")
