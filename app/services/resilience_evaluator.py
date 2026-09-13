from app.schemas_resilience import (
    ResilienceExperimentPolicy,
    ResilienceExperimentResult,
    ResilienceExperimentSample,
    ResilienceStrategy,
)

CONTROL_METRIC_NAMES: dict[ResilienceStrategy, str] = {
    ResilienceStrategy.RATE_LIMIT: "rate_limited_requests",
    ResilienceStrategy.GRACEFUL_DEGRADATION: "fallback_responses",
    ResilienceStrategy.FAULT_TOLERANCE: "replacement_events",
    ResilienceStrategy.AUTOSCALING: "scaling_events",
    ResilienceStrategy.ROLLBACK: "rollback_events",
}

STATEFUL_STRATEGIES: frozenset[ResilienceStrategy] = frozenset(
    {
        ResilienceStrategy.FAULT_TOLERANCE,
        ResilienceStrategy.ROLLBACK,
    }
)


def evaluate_resilience_experiment(
    sample: ResilienceExperimentSample,
    policy: ResilienceExperimentPolicy,
) -> ResilienceExperimentResult:
    expected_outcome_percent = round(
        sample.expected_outcome_count / sample.total_request_count * 100,
        4,
    )
    reasons: list[str] = []

    if expected_outcome_percent < policy.minimum_expected_outcome_percent:
        reasons.append("expected_outcome_below_target")
    if sample.control_event_count < policy.minimum_control_event_count:
        reasons.append("control_event_not_observed")
    if sample.recovery_time_seconds > policy.maximum_recovery_time_seconds:
        reasons.append("recovery_time_above_target")
    if not sample.service_recovered:
        reasons.append("service_not_recovered")
    if sample.strategy in STATEFUL_STRATEGIES and not sample.state_restored:
        reasons.append("state_not_restored")
    if sample.unexpected_error_count > policy.maximum_unexpected_error_count:
        reasons.append("unexpected_errors_detected")
    if sample.data_loss_count > policy.maximum_data_loss_count:
        reasons.append("data_loss_detected")

    return ResilienceExperimentResult(
        strategy=sample.strategy,
        control_metric_name=CONTROL_METRIC_NAMES[sample.strategy],
        total_request_count=sample.total_request_count,
        expected_outcome_count=sample.expected_outcome_count,
        expected_outcome_percent=expected_outcome_percent,
        unexpected_error_count=sample.unexpected_error_count,
        control_event_count=sample.control_event_count,
        recovery_time_seconds=sample.recovery_time_seconds,
        service_recovered=sample.service_recovered,
        state_restored=sample.state_restored,
        data_loss_count=sample.data_loss_count,
        passed=not reasons,
        reason_codes=reasons,
        evidence_refs=sample.evidence_refs,
        automated_mutation_allowed=False,
    )
