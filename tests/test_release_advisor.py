import pytest

from app.schemas_release_advice import ReleaseAdviceInput
from app.services.release_advisor import advise_release


def advice(
    *,
    release_status: str = "succeeded",
    risk_level: str | None = "low",
    burn_rate: float | None = 0.8,
    breached: bool | None = False,
):
    return advise_release(
        ReleaseAdviceInput(
            release_status=release_status,
            risk_level=risk_level,
            error_budget_burn_rate=burn_rate,
            slo_breached=breached,
            evidence_refs=["observation:1", "slo:1"],
        )
    )


def test_healthy_low_risk_release_can_proceed() -> None:
    result = advice()
    assert result.decision == "proceed"
    assert result.reason_codes == ["reliability_signals_within_policy"]


@pytest.mark.parametrize("risk_level", ["high", "critical"])
def test_high_risk_release_is_blocked(risk_level: str) -> None:
    result = advice(risk_level=risk_level)
    assert result.decision == "block"
    assert result.reason_codes == ["change_risk_too_high"]


@pytest.mark.parametrize("status", ["failed", "rolled_back"])
def test_unhealthy_release_is_blocked(status: str) -> None:
    result = advice(release_status=status)
    assert result.decision == "block"
    assert result.reason_codes == ["release_not_healthy"]


@pytest.mark.parametrize("status", ["queued", "running"])
def test_non_terminal_release_requires_review(status: str) -> None:
    result = advice(release_status=status)
    assert result.decision == "manual_review"
    assert result.reason_codes == ["release_not_terminal"]


def test_slo_breach_requires_review() -> None:
    result = advice(breached=True)
    assert result.decision == "manual_review"
    assert result.reason_codes == ["slo_breached"]


def test_burn_rate_at_one_requires_review() -> None:
    result = advice(burn_rate=1.0)
    assert result.decision == "manual_review"
    assert result.reason_codes == ["error_budget_burning_too_fast"]


def test_missing_signal_requires_review() -> None:
    result = advice(risk_level=None)
    assert result.decision == "manual_review"
    assert result.reason_codes == ["insufficient_reliability_evidence"]


def test_all_results_preserve_human_control() -> None:
    for result in (
        advice(),
        advice(risk_level="critical"),
        advice(breached=True),
    ):
        assert result.human_approval_required is True
        assert result.automated_mutation_allowed is False
        assert result.evidence_refs == ["observation:1", "slo:1"]
