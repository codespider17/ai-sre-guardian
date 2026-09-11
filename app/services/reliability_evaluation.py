from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Service, SLOEvaluationRecord, SLOPolicy
from app.schemas_reliability import SLIType, SLODefinition
from app.schemas_slo import (
    SLOEvaluationCreate,
    SLOEvaluationReceipt,
    SLOPolicyCreate,
    SLOPolicyReceipt,
)
from app.services.reliability_calculator import evaluate_slo


class ReliabilityServiceNotFoundError(Exception):
    pass


class SLOPolicyNotFoundError(Exception):
    pass


class SLOPolicyConflictError(Exception):
    pass


def decimal_value(value: float | int) -> Decimal:
    return Decimal(str(value))


def policy_receipt(
    policy: SLOPolicy,
    status: str,
) -> SLOPolicyReceipt:
    return SLOPolicyReceipt(
        status=status,
        policy_id=policy.id,
        service_id=policy.service_id,
        name=policy.name,
        sli_type=SLIType(policy.sli_type),
        objective_percent=float(policy.objective_percent),
        window_minutes=policy.window_minutes,
        active=policy.active,
    )


def evaluation_receipt(
    record: SLOEvaluationRecord,
    status: str,
) -> SLOEvaluationReceipt:
    return SLOEvaluationReceipt(
        status=status,
        evaluation_id=record.id,
        policy_id=record.policy_id,
        sample_key=record.sample_key,
        achieved_percent=float(record.achieved_percent),
        observed_bad_event_count=record.observed_bad_event_count,
        allowed_bad_event_count=float(record.allowed_bad_event_count),
        error_budget_percent=float(record.error_budget_percent),
        remaining_error_budget_percent=float(record.remaining_error_budget_percent),
        error_budget_consumption_percent=float(record.error_budget_consumption_percent),
        burn_rate=float(record.burn_rate),
        breached=record.breached,
        allowed_downtime_minutes=(
            float(record.allowed_downtime_minutes)
            if record.allowed_downtime_minutes is not None
            else None
        ),
        observed_downtime_minutes=(
            float(record.observed_downtime_minutes)
            if record.observed_downtime_minutes is not None
            else None
        ),
        sla_impact_minutes=(
            float(record.sla_impact_minutes)
            if record.sla_impact_minutes is not None
            else None
        ),
    )


def create_slo_policy(
    session: Session,
    request: SLOPolicyCreate,
) -> SLOPolicyReceipt:
    service = session.get(Service, request.service_id)
    if service is None:
        raise ReliabilityServiceNotFoundError(str(request.service_id))

    existing = session.scalar(
        select(SLOPolicy).where(
            SLOPolicy.service_id == request.service_id,
            SLOPolicy.name == request.name,
        )
    )
    if existing is not None:
        same_definition = (
            existing.sli_type == request.sli_type.value
            and existing.objective_percent == decimal_value(request.objective_percent)
            and existing.window_minutes == request.window_minutes
        )
        if not same_definition:
            raise SLOPolicyConflictError(request.name)
        return policy_receipt(existing, "duplicate")

    policy = SLOPolicy(
        service_id=request.service_id,
        name=request.name,
        sli_type=request.sli_type.value,
        objective_percent=decimal_value(request.objective_percent),
        window_minutes=request.window_minutes,
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return policy_receipt(policy, "created")


def evaluate_and_persist_slo(
    session: Session,
    policy_id: UUID,
    request: SLOEvaluationCreate,
) -> SLOEvaluationReceipt:
    policy = session.get(SLOPolicy, policy_id)
    if policy is None:
        raise SLOPolicyNotFoundError(str(policy_id))

    existing = session.scalar(
        select(SLOEvaluationRecord).where(
            SLOEvaluationRecord.policy_id == policy.id,
            SLOEvaluationRecord.sample_key == request.sample_key,
        )
    )
    if existing is not None:
        return evaluation_receipt(existing, "duplicate")

    definition = SLODefinition(
        name=policy.name,
        sli_type=SLIType(policy.sli_type),
        objective_percent=float(policy.objective_percent),
        window_minutes=policy.window_minutes,
    )
    evaluation = evaluate_slo(request.sample, definition)
    record = SLOEvaluationRecord(
        policy_id=policy.id,
        sample_key=request.sample_key,
        achieved_percent=decimal_value(evaluation.achieved_percent),
        observed_bad_event_count=(evaluation.observed_bad_event_count),
        allowed_bad_event_count=decimal_value(evaluation.allowed_bad_event_count),
        error_budget_percent=decimal_value(evaluation.error_budget_percent),
        remaining_error_budget_percent=decimal_value(
            evaluation.remaining_error_budget_percent
        ),
        error_budget_consumption_percent=decimal_value(
            evaluation.error_budget_consumption_percent
        ),
        burn_rate=decimal_value(evaluation.burn_rate),
        breached=evaluation.breached,
        allowed_downtime_minutes=(
            decimal_value(evaluation.allowed_downtime_minutes)
            if evaluation.allowed_downtime_minutes is not None
            else None
        ),
        observed_downtime_minutes=(
            decimal_value(evaluation.observed_downtime_minutes)
            if evaluation.observed_downtime_minutes is not None
            else None
        ),
        sla_impact_minutes=(
            decimal_value(evaluation.sla_impact_minutes)
            if evaluation.sla_impact_minutes is not None
            else None
        ),
        raw_sample=request.sample.model_dump(mode="json"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return evaluation_receipt(record, "evaluated")
