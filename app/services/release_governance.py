from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    ReleaseApproval,
    ReleaseObservation,
    ReleaseRecommendation,
)
from app.schemas_governance import (
    HumanApprovalCreate,
    HumanApprovalReceipt,
    ReleaseRecommendationCreate,
    ReleaseRecommendationReceipt,
)
from app.services.release_advisor import advise_release


class ReleaseObservationNotFoundError(Exception):
    pass


class ReleaseRecommendationNotFoundError(Exception):
    pass


class ReleaseGovernanceConflictError(Exception):
    pass


def optional_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def recommendation_receipt(
    model: ReleaseRecommendation,
    status: str,
) -> ReleaseRecommendationReceipt:
    return ReleaseRecommendationReceipt(
        status=status,
        recommendation_id=model.id,
        observation_id=model.observation_id,
        decision=model.decision,
        human_approval_required=model.human_approval_required,
        automated_mutation_allowed=model.automated_mutation_allowed,
        reason_codes=model.reason_codes,
        evidence_refs=model.evidence_refs,
        created_at=model.created_at,
    )


def approval_receipt(
    model: ReleaseApproval,
    status: str,
) -> HumanApprovalReceipt:
    return HumanApprovalReceipt(
        status=status,
        approval_id=model.id,
        recommendation_id=model.recommendation_id,
        decision=model.decision,
        actor=model.actor,
        reason=model.reason,
        decided_at=model.decided_at,
    )


def record_release_recommendation(
    session: Session,
    request: ReleaseRecommendationCreate,
) -> ReleaseRecommendationReceipt:
    observation = session.get(
        ReleaseObservation,
        request.observation_id,
    )
    if observation is None:
        raise ReleaseObservationNotFoundError(str(request.observation_id))
    if observation.status != request.signals.release_status.value:
        raise ReleaseGovernanceConflictError(
            "release status differs from the observation"
        )

    existing = session.scalar(
        select(ReleaseRecommendation).where(
            ReleaseRecommendation.observation_id == observation.id
        )
    )
    burn_rate = optional_decimal(request.signals.error_budget_burn_rate)
    if existing is not None:
        same_input = (
            existing.release_status == request.signals.release_status.value
            and existing.risk_level == request.signals.risk_level
            and existing.error_budget_burn_rate == burn_rate
            and existing.slo_breached == request.signals.slo_breached
            and existing.evidence_refs == request.signals.evidence_refs
        )
        if not same_input:
            raise ReleaseGovernanceConflictError(
                "observation already has a different recommendation"
            )
        return recommendation_receipt(existing, "duplicate")

    advice = advise_release(request.signals)
    recommendation = ReleaseRecommendation(
        observation_id=observation.id,
        release_status=request.signals.release_status.value,
        risk_level=request.signals.risk_level,
        error_budget_burn_rate=burn_rate,
        slo_breached=request.signals.slo_breached,
        decision=advice.decision,
        human_approval_required=advice.human_approval_required,
        automated_mutation_allowed=advice.automated_mutation_allowed,
        reason_codes=advice.reason_codes,
        evidence_refs=advice.evidence_refs,
    )
    session.add(recommendation)
    session.flush()
    session.add(
        AuditEvent(
            entity_type="release_recommendation",
            entity_id=recommendation.id,
            action="release.recommendation_recorded",
            actor="release-advisor",
            details={
                "decision": advice.decision,
                "observation_id": str(observation.id),
            },
        )
    )
    session.commit()
    session.refresh(recommendation)
    return recommendation_receipt(recommendation, "recorded")


def record_human_approval(
    session: Session,
    recommendation_id: UUID,
    request: HumanApprovalCreate,
) -> HumanApprovalReceipt:
    recommendation = session.get(
        ReleaseRecommendation,
        recommendation_id,
    )
    if recommendation is None:
        raise ReleaseRecommendationNotFoundError(str(recommendation_id))
    if recommendation.decision == "block" and request.decision == "approved":
        raise ReleaseGovernanceConflictError(
            "blocked recommendation cannot be approved"
        )

    existing = session.scalar(
        select(ReleaseApproval).where(
            ReleaseApproval.recommendation_id == recommendation.id
        )
    )
    if existing is not None:
        same_decision = (
            existing.decision == request.decision
            and existing.actor == request.actor
            and existing.reason == request.reason
        )
        if not same_decision:
            raise ReleaseGovernanceConflictError(
                "recommendation already has a different decision"
            )
        return approval_receipt(existing, "duplicate")

    approval = ReleaseApproval(
        recommendation_id=recommendation.id,
        decision=request.decision,
        actor=request.actor,
        reason=request.reason,
    )
    session.add(approval)
    session.flush()
    session.add(
        AuditEvent(
            entity_type="release_approval",
            entity_id=approval.id,
            action="release.human_decision_recorded",
            actor=request.actor,
            details={
                "decision": request.decision,
                "recommendation_id": str(recommendation.id),
            },
        )
    )
    session.commit()
    session.refresh(approval)
    return approval_receipt(approval, "recorded")
