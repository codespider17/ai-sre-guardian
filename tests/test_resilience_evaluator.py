import pytest
from pydantic import ValidationError

from app.schemas_resilience import (
    ResilienceExperimentPolicy,
    ResilienceExperimentSample,
    ResilienceStrategy,
)
from app.services.resilience_evaluator import (
    CONTROL_METRIC_NAMES,
    evaluate_resilience_experiment,
)


def policy() -> ResilienceExperimentPolicy:
    return ResilienceExperimentPolicy(
        minimum_expected_outcome_percent=99,
        minimum_control_event_count=1,
        maximum_recovery_time_seconds=60,
        maximum_unexpected_error_count=0,
        maximum_data_loss_count=0,
    )


def sample(
    strategy: ResilienceStrategy,
    **overrides: object,
) -> ResilienceExperimentSample:
    values: dict[str, object] = {
        "strategy": strategy,
        "total_request_count": 1000,
        "expected_outcome_count": 1000,
        "unexpected_error_count": 0,
        "control_event_count": 1,
        "recovery_time_seconds": 15,
        "service_recovered": True,
        "state_restored": True,
        "data_loss_count": 0,
        "evidence_refs": [f"experiment:{strategy.value}"],
    }
    values.update(overrides)
    return ResilienceExperimentSample.model_validate(values)


@pytest.mark.parametrize("strategy", list(ResilienceStrategy))
def test_all_five_strategies_pass(
    strategy: ResilienceStrategy,
) -> None:
    result = evaluate_resilience_experiment(sample(strategy), policy())
    assert result.passed is True
    assert result.reason_codes == []
    assert result.expected_outcome_percent == 100
    assert result.automated_mutation_allowed is False


@pytest.mark.parametrize(
    ("strategy", "metric_name"),
    list(CONTROL_METRIC_NAMES.items()),
)
def test_each_strategy_has_a_control_metric(
    strategy: ResilienceStrategy,
    metric_name: str,
) -> None:
    result = evaluate_resilience_experiment(sample(strategy), policy())
    assert result.control_metric_name == metric_name


def test_reports_all_failure_reasons_in_stable_order() -> None:
    result = evaluate_resilience_experiment(
        sample(
            ResilienceStrategy.ROLLBACK,
            expected_outcome_count=800,
            unexpected_error_count=100,
            control_event_count=0,
            recovery_time_seconds=61,
            service_recovered=False,
            state_restored=False,
            data_loss_count=1,
        ),
        policy(),
    )
    assert result.passed is False
    assert result.reason_codes == [
        "expected_outcome_below_target",
        "control_event_not_observed",
        "recovery_time_above_target",
        "service_not_recovered",
        "state_not_restored",
        "unexpected_errors_detected",
        "data_loss_detected",
    ]


def test_classified_outcomes_cannot_exceed_total_requests() -> None:
    with pytest.raises(ValidationError):
        sample(
            ResilienceStrategy.RATE_LIMIT,
            expected_outcome_count=950,
            unexpected_error_count=51,
        )


def test_evidence_references_must_be_unique() -> None:
    with pytest.raises(ValidationError):
        sample(
            ResilienceStrategy.AUTOSCALING,
            evidence_refs=["metric:hpa", "metric:hpa"],
        )


@pytest.mark.parametrize(
    "strategy",
    [
        ResilienceStrategy.FAULT_TOLERANCE,
        ResilienceStrategy.ROLLBACK,
    ],
)
def test_stateful_strategies_require_state_restoration(
    strategy: ResilienceStrategy,
) -> None:
    result = evaluate_resilience_experiment(
        sample(strategy, state_restored=False),
        policy(),
    )
    assert result.reason_codes == ["state_not_restored"]


def test_stateless_strategy_does_not_require_state_restoration() -> None:
    result = evaluate_resilience_experiment(
        sample(
            ResilienceStrategy.RATE_LIMIT,
            state_restored=False,
        ),
        policy(),
    )
    assert result.passed is True


def test_policy_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        ResilienceExperimentPolicy(
            minimum_expected_outcome_percent=101,
            minimum_control_event_count=0,
            maximum_recovery_time_seconds=0,
            maximum_unexpected_error_count=-1,
            maximum_data_loss_count=-1,
        )
