import json
from typing import Any

import httpx

from app.schemas_ai import (
    AIAnalysisOutcome,
    DeepSeekAnalysisInput,
    StructuredAIAnalysis,
)

DEEPSEEK_CHAT_PATH = "/chat/completions"
DEEPSEEK_RESPONSE_FORMAT = {"type": "json_object"}
MAX_OUTPUT_TOKENS = 1600


class DeepSeekAnalysisError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class DeepSeekAnalysisClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-flash",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("deepseek api key is required")
        if max_retries < 0 or max_retries > 3:
            raise ValueError("deepseek max retries must be between 0 and 3")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport

    def _payload(self, analysis_input: DeepSeekAnalysisInput) -> dict[str, Any]:
        system_prompt = (
            "You are an SRE change-risk reviewer. Return exactly one JSON object. "
            "Use only the supplied evidence_ref values. Never invent evidence. "
            "The JSON keys must be risk_level, summary, recommendation, confidence, "
            "evidence_refs and reasoning_points. recommendation must be proceed, "
            "manual_review_required or block. risk_level must be low, medium, "
            "high or critical. confidence must be a JSON number from 0 to 1. "
            "evidence_refs must contain 1 to 10 exact supplied evidence_ref "
            "values. reasoning_points must contain 1 to 6 short strings. "
            "Do not use Markdown or code fences."
        )
        user_payload = {
            "change_summary": analysis_input.change_summary,
            "deterministic_risk_score": analysis_input.deterministic_risk_score,
            "deterministic_risk_level": analysis_input.deterministic_risk_level,
            "evidence": [item.model_dump() for item in analysis_input.evidence],
        }
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "response_format": DEEPSEEK_RESPONSE_FORMAT,
            "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUTPUT_TOKENS,
            "stream": False,
        }

    def analyze(
        self,
        analysis_input: DeepSeekAnalysisInput,
    ) -> StructuredAIAnalysis:
        payload = self._payload(analysis_input)
        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = client.post(
                        self._base_url + DEEPSEEK_CHAT_PATH,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                break
            except httpx.HTTPError:
                if attempt == self._max_retries:
                    raise DeepSeekAnalysisError("provider_unavailable") from None

        if response is None:
            raise DeepSeekAnalysisError("provider_unavailable")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model content")
            analysis = StructuredAIAnalysis.model_validate_json(content)
        except (
            IndexError,
            KeyError,
            TypeError,
            ValueError,
        ):
            raise DeepSeekAnalysisError("invalid_provider_response") from None

        allowed_refs = {evidence.evidence_ref for evidence in analysis_input.evidence}
        if not set(analysis.evidence_refs).issubset(allowed_refs):
            raise DeepSeekAnalysisError("untrusted_evidence_reference")
        return analysis


def _rules_fallback(
    analysis_input: DeepSeekAnalysisInput,
) -> StructuredAIAnalysis:
    score = analysis_input.deterministic_risk_score
    if score >= 70:
        recommendation = "block"
    elif score >= 40:
        recommendation = "manual_review_required"
    else:
        recommendation = "proceed"
    return StructuredAIAnalysis(
        risk_level=analysis_input.deterministic_risk_level,
        summary=(
            "Deterministic fallback applied because the AI provider result "
            "was unavailable or invalid."
        ),
        recommendation=recommendation,
        confidence=1.0,
        evidence_refs=[evidence.evidence_ref for evidence in analysis_input.evidence],
        reasoning_points=[
            f"deterministic_risk_score={score}",
            f"deterministic_risk_level={analysis_input.deterministic_risk_level}",
        ],
    )


def analyze_with_fallback(
    analysis_input: DeepSeekAnalysisInput,
    client: DeepSeekAnalysisClient,
) -> AIAnalysisOutcome:
    try:
        analysis = client.analyze(analysis_input)
    except DeepSeekAnalysisError as exc:
        return AIAnalysisOutcome(
            mode="rules_fallback",
            model=None,
            analysis=_rules_fallback(analysis_input),
            fallback_reason=exc.code,
        )
    return AIAnalysisOutcome(
        mode="deepseek",
        model=client.model,
        analysis=analysis,
    )
