import json
from typing import Any

import httpx
import pytest

from app.schemas_ai import AnalysisEvidence, DeepSeekAnalysisInput
from app.services.deepseek_analysis import (
    DEEPSEEK_CHAT_PATH,
    DeepSeekAnalysisClient,
    DeepSeekAnalysisError,
    analyze_with_fallback,
)


def analysis_input(score: int = 72) -> DeepSeekAnalysisInput:
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"
    return DeepSeekAnalysisInput(
        change_summary="database and deployment change",
        deterministic_risk_score=score,
        deterministic_risk_level=level,
        evidence=[
            AnalysisEvidence(
                evidence_ref="evidence-1",
                source_type="change_risk",
                content="database migration detected",
            ),
            AnalysisEvidence(
                evidence_ref="knowledge-1",
                source_type="knowledge",
                content="review rollback readiness",
            ),
        ],
    )


def model_content(
    *,
    evidence_refs: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "risk_level": "high",
            "summary": "High-risk change requires approval.",
            "recommendation": "manual_review_required",
            "confidence": 0.91,
            "evidence_refs": evidence_refs or ["evidence-1", "knowledge-1"],
            "reasoning_points": ["migration detected", "rollback review needed"],
        }
    )


def client_for(
    handler: Any,
    *,
    api_key: str = "unit-test-key",
    max_retries: int = 0,
) -> DeepSeekAnalysisClient:
    return DeepSeekAnalysisClient(
        api_key=api_key,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def test_valid_json_response_is_schema_validated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": model_content()}}]},
        )

    outcome = analyze_with_fallback(analysis_input(), client_for(handler))
    assert outcome.mode == "deepseek"
    assert outcome.model == "deepseek-v4-flash"
    assert outcome.analysis.confidence == 0.91


def test_request_matches_official_json_contract() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": model_content()}}]},
        )

    analyze_with_fallback(analysis_input(), client_for(handler))
    assert captured["path"] == DEEPSEEK_CHAT_PATH
    assert captured["authorization"] == "Bearer unit-test-key"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["max_tokens"] == 1600
    assert "json" in captured["payload"]["messages"][0]["content"].lower()
    assert "1 to 6 short strings" in captured["payload"]["messages"][0]["content"]


def test_http_failure_uses_rules_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    outcome = analyze_with_fallback(analysis_input(), client_for(handler))
    assert outcome.mode == "rules_fallback"
    assert outcome.fallback_reason == "provider_unavailable"


def test_invalid_json_uses_rules_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    outcome = analyze_with_fallback(analysis_input(), client_for(handler))
    assert outcome.fallback_reason == "invalid_provider_response"


def test_untrusted_evidence_reference_uses_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": model_content(evidence_refs=["invented"])}}
                ]
            },
        )

    outcome = analyze_with_fallback(analysis_input(), client_for(handler))
    assert outcome.fallback_reason == "untrusted_evidence_reference"


def test_empty_content_uses_rules_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": ""}}]},
        )

    outcome = analyze_with_fallback(analysis_input(), client_for(handler))
    assert outcome.fallback_reason == "invalid_provider_response"


@pytest.mark.parametrize(
    ("score", "expected_recommendation"),
    [(90, "block"), (55, "manual_review_required"), (20, "proceed")],
)
def test_fallback_recommendation_is_deterministic(
    score: int,
    expected_recommendation: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    outcome = analyze_with_fallback(analysis_input(score), client_for(handler))
    assert outcome.analysis.recommendation == expected_recommendation
    assert outcome.analysis.confidence == 1.0


def test_provider_exception_does_not_expose_api_key() -> None:
    api_key = "sensitive-unit-test-value"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unavailable", request=request)

    client = client_for(handler, api_key=api_key)
    with pytest.raises(DeepSeekAnalysisError) as captured:
        client.analyze(analysis_input())
    assert api_key not in str(captured.value)
    assert captured.value.__cause__ is None
