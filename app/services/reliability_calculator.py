from app.schemas_reliability import (
    ReliabilitySample,
    SLIResult,
    SLIType,
    SLODefinition,
    SLOEvaluation,
)

DEFAULT_SLOS = (
    SLODefinition(
        name="availability-99.9",
        sli_type=SLIType.AVAILABILITY,
        objective_percent=99.9,
        window_minutes=43_200,
    ),
    SLODefinition(
        name="latency-compliance-99.0",
        sli_type=SLIType.LATENCY_COMPLIANCE,
        objective_percent=99.0,
        window_minutes=43_200,
    ),
)


def _rounded(value: float) -> float:
    return round(value, 6)


def _percent(numerator: int, denominator: int) -> float:
    return _rounded(numerator / denominator * 100)


def calculate_slis(
    sample: ReliabilitySample,
) -> dict[SLIType, SLIResult]:
    failed_requests = sample.total_requests - sample.successful_requests

    return {
        SLIType.AVAILABILITY: SLIResult(
            sli_type=SLIType.AVAILABILITY,
            value_percent=_percent(
                sample.successful_requests,
                sample.total_requests,
            ),
            numerator=sample.successful_requests,
            denominator=sample.total_requests,
        ),
        SLIType.ERROR_RATE: SLIResult(
            sli_type=SLIType.ERROR_RATE,
            value_percent=_percent(
                failed_requests,
                sample.total_requests,
            ),
            numerator=failed_requests,
            denominator=sample.total_requests,
        ),
        SLIType.LATENCY_COMPLIANCE: SLIResult(
            sli_type=SLIType.LATENCY_COMPLIANCE,
            value_percent=_percent(
                sample.latency_good_requests,
                sample.total_requests,
            ),
            numerator=sample.latency_good_requests,
            denominator=sample.total_requests,
        ),
        SLIType.SATURATION_COMPLIANCE: SLIResult(
            sli_type=SLIType.SATURATION_COMPLIANCE,
            value_percent=_percent(
                sample.saturation_good_samples,
                sample.saturation_sample_count,
            ),
            numerator=sample.saturation_good_samples,
            denominator=sample.saturation_sample_count,
        ),
    }


def evaluate_slo(
    sample: ReliabilitySample,
    definition: SLODefinition,
) -> SLOEvaluation:
    supported_slos = {
        SLIType.AVAILABILITY,
        SLIType.LATENCY_COMPLIANCE,
    }
    if definition.sli_type not in supported_slos:
        raise ValueError("SLO evaluation supports availability and latency compliance")

    if (
        definition.sli_type == SLIType.AVAILABILITY
        and sample.downtime_minutes > definition.window_minutes
    ):
        raise ValueError("downtime cannot exceed the SLO window")

    sli = calculate_slis(sample)[definition.sli_type]
    observed_bad_events = sli.denominator - sli.numerator
    error_budget_percent = 100 - definition.objective_percent
    observed_bad_percent = 100 - sli.value_percent
    allowed_bad_events = sli.denominator * error_budget_percent / 100
    burn_rate = observed_bad_percent / error_budget_percent

    allowed_downtime: float | None = None
    observed_downtime: float | None = None
    sla_impact: float | None = None

    if definition.sli_type == SLIType.AVAILABILITY:
        allowed_downtime = definition.window_minutes * error_budget_percent / 100
        observed_downtime = sample.downtime_minutes
        sla_impact = max(observed_downtime - allowed_downtime, 0)

    return SLOEvaluation(
        name=definition.name,
        sli_type=definition.sli_type,
        objective_percent=definition.objective_percent,
        achieved_percent=sli.value_percent,
        observed_bad_event_count=observed_bad_events,
        allowed_bad_event_count=_rounded(allowed_bad_events),
        error_budget_percent=_rounded(error_budget_percent),
        remaining_error_budget_percent=_rounded(
            max(error_budget_percent - observed_bad_percent, 0)
        ),
        error_budget_consumption_percent=_rounded(burn_rate * 100),
        burn_rate=_rounded(burn_rate),
        breached=sli.value_percent < definition.objective_percent,
        allowed_downtime_minutes=(
            None if allowed_downtime is None else _rounded(allowed_downtime)
        ),
        observed_downtime_minutes=observed_downtime,
        sla_impact_minutes=(None if sla_impact is None else _rounded(sla_impact)),
    )
