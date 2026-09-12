from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (
    AuditEvent,
    ReleaseObservation,
    Service,
)
from app.schemas_governance import (
    HumanApprovalCreate,
    ReleaseRecommendationCreate,
)
from app.schemas_release_advice import ReleaseAdviceInput
from app.services.release_governance import (
    ReleaseGovernanceConflictError,
    ReleaseObservationNotFoundError,
    ReleaseRecommendationNotFoundError,
    record_human_approval,
    record_release_recommendation,
)


def create_observation(session, status: str = "succeeded"):
    token = uuid4().hex
    service = Service(
        name=f"governance-{token}",
        repository_full_name=f"codespider17/governance-{token}",
        namespace="ai-sre-system",
        workload_name="ai-sre-guardian",
    )
    session.add(service)
    session.flush()
    observation = ReleaseObservation(
        service_id=service.id,
        delivery_id=f"governance-{token}",
        source="devflow",
        source_pipeline_run_id=uuid4(),
        source_deployment_id=uuid4(),
        environment="development",
        commit_sha="b" * 40,
        image_reference="hb.reg.com/devflow/api:" + "b" * 40,
        status=status,
        raw_event={"status": status},
        observed_at=datetime.now(UTC),
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)
    return observation


def recommendation_request(
    observation_id,
    *,
    status: str = "succeeded",
    risk_level: str = "medium",
    burn_rate: float = 1.3,
    breached: bool = True,
):
    return ReleaseRecommendationCreate(
        observation_id=observation_id,
        signals=ReleaseAdviceInput(
            release_status=status,
            risk_level=risk_level,
            error_budget_burn_rate=burn_rate,
            slo_breached=breached,
            evidence_refs=[f"observation:{observation_id}"],
        ),
    )


def approval_request(decision: str = "approved"):
    return HumanApprovalCreate(
        decision=decision,
        actor="platform-approver",
        reason="reviewed reliability evidence",
    )


def test_persists_recommendation_and_audit() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        result = record_release_recommendation(
            session,
            recommendation_request(observation.id),
        )
        audit_count = session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.entity_id == result.recommendation_id,
                AuditEvent.action == "release.recommendation_recorded",
            )
        )
        assert result.status == "recorded"
        assert result.decision == "manual_review"
        assert audit_count == 1


def test_duplicate_recommendation_reuses_record() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        request = recommendation_request(observation.id)
        first = record_release_recommendation(session, request)
        second = record_release_recommendation(session, request)
        assert second.status == "duplicate"
        assert first.recommendation_id == second.recommendation_id


def test_observation_status_mismatch_is_rejected() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        request = recommendation_request(
            observation.id,
            status="failed",
        )
        with pytest.raises(ReleaseGovernanceConflictError):
            record_release_recommendation(session, request)


def test_persists_human_approval_and_audit() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        recommendation = record_release_recommendation(
            session,
            recommendation_request(observation.id),
        )
        approval = record_human_approval(
            session,
            recommendation.recommendation_id,
            approval_request(),
        )
        audit_count = session.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.entity_id == approval.approval_id,
                AuditEvent.action == "release.human_decision_recorded",
            )
        )
        assert approval.status == "recorded"
        assert approval.decision == "approved"
        assert audit_count == 1


def test_duplicate_approval_reuses_record() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        recommendation = record_release_recommendation(
            session,
            recommendation_request(observation.id),
        )
        request = approval_request()
        first = record_human_approval(
            session,
            recommendation.recommendation_id,
            request,
        )
        second = record_human_approval(
            session,
            recommendation.recommendation_id,
            request,
        )
        assert second.status == "duplicate"
        assert first.approval_id == second.approval_id


def test_conflicting_approval_is_rejected() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        recommendation = record_release_recommendation(
            session,
            recommendation_request(observation.id),
        )
        record_human_approval(
            session,
            recommendation.recommendation_id,
            approval_request(),
        )
        with pytest.raises(ReleaseGovernanceConflictError):
            record_human_approval(
                session,
                recommendation.recommendation_id,
                approval_request("rejected"),
            )


def test_blocked_recommendation_cannot_be_approved() -> None:
    with SessionLocal() as session:
        observation = create_observation(session)
        recommendation = record_release_recommendation(
            session,
            recommendation_request(
                observation.id,
                risk_level="critical",
                burn_rate=0.8,
                breached=False,
            ),
        )
        with pytest.raises(ReleaseGovernanceConflictError):
            record_human_approval(
                session,
                recommendation.recommendation_id,
                approval_request(),
            )


def test_unknown_entities_are_rejected() -> None:
    with SessionLocal() as session:
        with pytest.raises(ReleaseObservationNotFoundError):
            record_release_recommendation(
                session,
                recommendation_request(uuid4()),
            )
        with pytest.raises(ReleaseRecommendationNotFoundError):
            record_human_approval(
                session,
                uuid4(),
                approval_request(),
            )
