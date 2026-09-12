from app.schemas_devflow import DevFlowReleaseStatus
from app.schemas_release_advice import (
    ReleaseAdviceInput,
    ReleaseAdviceResult,
    ReleaseDecision,
)


def advise_release(request: ReleaseAdviceInput) -> ReleaseAdviceResult:
    reasons: list[str] = []
    decision: ReleaseDecision

    if request.release_status in {
        DevFlowReleaseStatus.FAILED,
        DevFlowReleaseStatus.ROLLED_BACK,
    }:
        decision = "block"
        reasons.append("release_not_healthy")
    elif request.risk_level in {"high", "critical"}:
        decision = "block"
        reasons.append("change_risk_too_high")
    elif request.release_status in {
        DevFlowReleaseStatus.QUEUED,
        DevFlowReleaseStatus.RUNNING,
    }:
        decision = "manual_review"
        reasons.append("release_not_terminal")
    elif request.slo_breached is True:
        decision = "manual_review"
        reasons.append("slo_breached")
    elif (
        request.error_budget_burn_rate is not None
        and request.error_budget_burn_rate >= 1
    ):
        decision = "manual_review"
        reasons.append("error_budget_burning_too_fast")
    elif (
        request.risk_level is None
        or request.slo_breached is None
        or request.error_budget_burn_rate is None
    ):
        decision = "manual_review"
        reasons.append("insufficient_reliability_evidence")
    else:
        decision = "proceed"
        reasons.append("reliability_signals_within_policy")

    return ReleaseAdviceResult(
        decision=decision,
        human_approval_required=True,
        automated_mutation_allowed=False,
        reason_codes=reasons,
        evidence_refs=request.evidence_refs,
    )
