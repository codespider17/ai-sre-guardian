from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Service, SLOEvaluationRecord, SLOPolicy
from app.schemas_reliability import ReliabilitySample
from app.services.reliability_calculator import DEFAULT_SLOS, evaluate_slo


def create_service(session: Session) -> Service:
    token = uuid4().hex
    service = Service(
        name=f"reliability-{token}",
        repository_full_name=f"codespider17/reliability-{token}",
        namespace="ai-sre-system",
        workload_name="ai-sre-guardian",
    )
    session.add(service)
    session.flush()
    return service


def decimal_value(value: float | int) -> Decimal:
    return Decimal(str(value))


def build_record(
    policy: SLOPolicy,
    sample_key: str,
    sample: ReliabilitySample,
) -> SLOEvaluationRecord:
    evaluation = evaluate_slo(
        sample,
        next(
            definition for definition in DEFAULT_SLOS if definition.name == policy.name
        ),
    )
    return SLOEvaluationRecord(
        policy_id=policy.id,
        sample_key=sample_key,
        achieved_percent=decimal_value(evaluation.achieved_percent),
        observed_bad_event_count=evaluation.observed_bad_event_count,
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
        raw_sample=sample.model_dump(mode="json"),
    )


def test_persists_two_policies_and_evaluations() -> None:
    sample = ReliabilitySample(
        total_requests=1_000_000,
        successful_requests=998_700,
        latency_good_requests=992_000,
        saturation_sample_count=1_000,
        saturation_good_samples=950,
        downtime_minutes=60,
    )

    with SessionLocal() as session:
        service = create_service(session)
        policies = [
            SLOPolicy(
                service_id=service.id,
                name=definition.name,
                sli_type=definition.sli_type.value,
                objective_percent=decimal_value(definition.objective_percent),
                window_minutes=definition.window_minutes,
            )
            for definition in DEFAULT_SLOS
        ]
        session.add_all(policies)
        session.flush()
        records = [build_record(policy, "sample-001", sample) for policy in policies]
        session.add_all(records)
        session.commit()

        policy_count = session.scalar(
            select(func.count(SLOPolicy.id)).where(SLOPolicy.service_id == service.id)
        )
        record_count = session.scalar(
            select(func.count(SLOEvaluationRecord.id)).where(
                SLOEvaluationRecord.policy_id.in_([policy.id for policy in policies])
            )
        )

        assert policy_count == 2
        assert record_count == 2
        assert records[0].breached is True
        assert records[0].burn_rate == Decimal("1.300000")
        assert records[0].sla_impact_minutes == Decimal("16.800000")
        assert records[1].breached is False


def test_policy_name_is_unique_per_service() -> None:
    with SessionLocal() as session:
        service = create_service(session)
        session.add_all(
            [
                SLOPolicy(
                    service_id=service.id,
                    name="availability-99.9",
                    sli_type="availability",
                    objective_percent=Decimal("99.900"),
                    window_minutes=43_200,
                ),
                SLOPolicy(
                    service_id=service.id,
                    name="availability-99.9",
                    sli_type="availability",
                    objective_percent=Decimal("99.900"),
                    window_minutes=43_200,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_sample_key_is_unique_per_policy() -> None:
    sample = ReliabilitySample(
        total_requests=10_000,
        successful_requests=9_999,
        latency_good_requests=9_950,
        saturation_sample_count=100,
        saturation_good_samples=95,
        downtime_minutes=1,
    )

    with SessionLocal() as session:
        service = create_service(session)
        definition = DEFAULT_SLOS[0]
        policy = SLOPolicy(
            service_id=service.id,
            name=definition.name,
            sli_type=definition.sli_type.value,
            objective_percent=decimal_value(definition.objective_percent),
            window_minutes=definition.window_minutes,
        )
        session.add(policy)
        session.flush()
        session.add_all(
            [
                build_record(policy, "duplicate-sample", sample),
                build_record(policy, "duplicate-sample", sample),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
