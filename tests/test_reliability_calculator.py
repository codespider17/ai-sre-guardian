import pytest
from pydantic import ValidationError

from app.schemas_reliability import (
    ReliabilitySample,
    SLIType,
    SLODefinition,
)
from app.services.reliability_calculator import (
    DEFAULT_SLOS,
    calculate_slis,
    evaluate_slo,
)


def sample() -> ReliabilitySample:
    return ReliabilitySample(
        total_requests=1_000_000,
        successful_requests=998_700,
        latency_good_requests=992_000,
        saturation_sample_count=1_000,
        saturation_good_samples=950,
        downtime_minutes=60,
    )


def test_calculates_four_slis() -> None:
    results = calculate_slis(sample())

    assert len(results) == 4
    assert results[SLIType.AVAILABILITY].value_percent == 99.87
    assert results[SLIType.ERROR_RATE].value_percent == 0.13
    assert results[SLIType.LATENCY_COMPLIANCE].value_percent == 99.2
    assert results[SLIType.SATURATION_COMPLIANCE].value_percent == 95.0


def test_defines_two_default_slos() -> None:
    assert len(DEFAULT_SLOS) == 2
    assert DEFAULT_SLOS[0].objective_percent == 99.9
    assert DEFAULT_SLOS[1].objective_percent == 99.0


def test_availability_slo_calculates_budget_burn_and_sla_impact() -> None:
    evaluation = evaluate_slo(sample(), DEFAULT_SLOS[0])

    assert evaluation.achieved_percent == 99.87
    assert evaluation.error_budget_percent == pytest.approx(0.1)
    assert evaluation.observed_bad_event_count == 1_300
    assert evaluation.allowed_bad_event_count == pytest.approx(1_000)
    assert evaluation.burn_rate == pytest.approx(1.3)
    assert evaluation.error_budget_consumption_percent == 130
    assert evaluation.remaining_error_budget_percent == 0
    assert evaluation.allowed_downtime_minutes == pytest.approx(43.2)
    assert evaluation.sla_impact_minutes == pytest.approx(16.8)
    assert evaluation.breached is True


def test_latency_slo_remains_inside_budget() -> None:
    evaluation = evaluate_slo(sample(), DEFAULT_SLOS[1])

    assert evaluation.achieved_percent == 99.2
    assert evaluation.observed_bad_event_count == 8_000
    assert evaluation.allowed_bad_event_count == 10_000
    assert evaluation.burn_rate == pytest.approx(0.8)
    assert evaluation.error_budget_consumption_percent == 80
    assert evaluation.remaining_error_budget_percent == pytest.approx(0.2)
    assert evaluation.sla_impact_minutes is None
    assert evaluation.breached is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("successful_requests", 1_000_001),
        ("latency_good_requests", 1_000_001),
        ("saturation_good_samples", 1_001),
    ],
)
def test_rejects_counters_larger_than_denominator(
    field: str,
    value: int,
) -> None:
    payload = sample().model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        ReliabilitySample.model_validate(payload)


def test_rejects_unsupported_error_rate_slo() -> None:
    definition = SLODefinition(
        name="invalid-error-rate-slo",
        sli_type=SLIType.ERROR_RATE,
        objective_percent=99,
        window_minutes=60,
    )

    with pytest.raises(ValueError, match="supports availability"):
        evaluate_slo(sample(), definition)


def test_rejects_downtime_larger_than_window() -> None:
    definition = SLODefinition(
        name="short-window",
        sli_type=SLIType.AVAILABILITY,
        objective_percent=99,
        window_minutes=30,
    )

    with pytest.raises(ValueError, match="downtime"):
        evaluate_slo(sample(), definition)


def test_perfect_sample_has_zero_budget_consumption() -> None:
    perfect = ReliabilitySample(
        total_requests=10_000,
        successful_requests=10_000,
        latency_good_requests=10_000,
        saturation_sample_count=100,
        saturation_good_samples=100,
        downtime_minutes=0,
    )

    evaluation = evaluate_slo(perfect, DEFAULT_SLOS[0])

    assert evaluation.achieved_percent == 100
    assert evaluation.burn_rate == 0
    assert evaluation.error_budget_consumption_percent == 0
    assert evaluation.sla_impact_minutes == 0
    assert evaluation.breached is False
