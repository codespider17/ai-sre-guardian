import pytest
from pydantic import ValidationError

from app.schemas_capacity import (
    CapacityBaselinePolicy,
    CapacityBaselineSample,
)
from app.services.capacity_baseline import calculate_capacity_baseline


def policy() -> CapacityBaselinePolicy:
    return CapacityBaselinePolicy(
        minimum_requests_per_second=75,
        maximum_p95_latency_ms=250,
        maximum_error_rate_percent=0.5,
        maximum_cpu_millicores=700,
        maximum_memory_mib=384,
    )


def sample(**overrides: object) -> CapacityBaselineSample:
    values: dict[str, object] = {
        "virtual_users": 50,
        "duration_seconds": 60,
        "total_requests": 5000,
        "failed_requests": 10,
        "p95_latency_ms": 180,
        "peak_cpu_millicores": 420,
        "peak_memory_mib": 220,
        "initial_replicas": 1,
        "peak_replicas": 3,
        "evidence_refs": [
            "k6:planned-capacity-run",
            "prometheus:planned-resource-sample",
            "hpa:planned-scale-observation",
        ],
    }
    values.update(overrides)
    return CapacityBaselineSample.model_validate(values)


def test_healthy_sample_passes_and_calculates_metrics() -> None:
    result = calculate_capacity_baseline(sample(), policy())
    assert result.passed is True
    assert result.requests_per_second == 83.3333
    assert result.successful_requests_per_second == 83.1667
    assert result.error_rate_percent == 0.2
    assert result.successful_requests == 4990


def test_calculates_resource_efficiency_and_scaling() -> None:
    result = calculate_capacity_baseline(sample(), policy())
    assert result.requests_per_cpu_core == 198.4127
    assert result.requests_per_memory_gib == 387.8788
    assert result.scale_out_ratio == 3.0


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"total_requests": 3000}, "throughput_below_target"),
        ({"p95_latency_ms": 251}, "p95_latency_above_target"),
        ({"failed_requests": 26}, "error_rate_above_target"),
        ({"peak_cpu_millicores": 701}, "cpu_above_target"),
        ({"peak_memory_mib": 385}, "memory_above_target"),
    ],
)
def test_single_capacity_limit_is_reported(
    overrides: dict[str, object],
    reason: str,
) -> None:
    result = calculate_capacity_baseline(sample(**overrides), policy())
    assert result.passed is False
    assert result.limit_reason_codes == [reason]


def test_multiple_capacity_limits_preserve_all_reasons() -> None:
    result = calculate_capacity_baseline(
        sample(
            total_requests=2000,
            failed_requests=100,
            p95_latency_ms=900,
            peak_cpu_millicores=900,
            peak_memory_mib=600,
        ),
        policy(),
    )
    assert result.passed is False
    assert len(result.limit_reason_codes) == 5


def test_failed_requests_cannot_exceed_total_requests() -> None:
    with pytest.raises(ValidationError):
        sample(total_requests=10, failed_requests=11)


def test_peak_replicas_cannot_be_below_initial_replicas() -> None:
    with pytest.raises(ValidationError):
        sample(initial_replicas=3, peak_replicas=2)


def test_policy_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValidationError):
        CapacityBaselinePolicy(
            minimum_requests_per_second=0,
            maximum_p95_latency_ms=250,
            maximum_error_rate_percent=101,
            maximum_cpu_millicores=700,
            maximum_memory_mib=384,
        )
