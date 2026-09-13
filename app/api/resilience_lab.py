from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from secrets import compare_digest
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from prometheus_client import Counter

from app.schemas_resilience_lab import (
    DegradationExperimentReceipt,
    DegradationExperimentRequest,
    RateLimitExperimentReceipt,
    RateLimitExperimentRequest,
)
from app.settings import get_settings

RATE_LIMIT_MAX_REQUESTS = 3
RATE_LIMIT_WINDOW_SECONDS = 10

RESILIENCE_REQUESTS = Counter(
    "ai_sre_resilience_requests_total",
    "Resilience lab requests grouped by strategy and outcome.",
    ("strategy", "outcome"),
)
RESILIENCE_CONTROL_EVENTS = Counter(
    "ai_sre_resilience_control_events_total",
    "Resilience lab control events grouped by strategy and event.",
    ("strategy", "event"),
)


@dataclass
class RateLimitWindow:
    started_at: float
    request_count: int


_rate_limit_windows: dict[str, RateLimitWindow] = {}
_rate_limit_lock = Lock()
_clock: Callable[[], float] = monotonic

router = APIRouter(
    prefix="/api/v1/resilience-lab",
    tags=["resilience-lab"],
)


def authorize_resilience_lab(
    token: Annotated[
        str | None,
        Header(alias="X-Resilience-Lab-Token"),
    ] = None,
) -> None:
    expected = get_settings().resilience_lab_token
    if token is None or not compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid resilience lab token",
        )


ResilienceLabAuthorization = Annotated[
    None,
    Depends(authorize_resilience_lab),
]


def reset_rate_limit_state() -> None:
    with _rate_limit_lock:
        _rate_limit_windows.clear()


def consume_rate_limit(client_id: str) -> tuple[bool, int, int]:
    now = _clock()
    with _rate_limit_lock:
        expired_clients = [
            key
            for key, value in _rate_limit_windows.items()
            if now - value.started_at >= RATE_LIMIT_WINDOW_SECONDS
        ]
        for key in expired_clients:
            del _rate_limit_windows[key]

        window = _rate_limit_windows.get(client_id)
        if window is None:
            window = RateLimitWindow(started_at=now, request_count=0)
            _rate_limit_windows[client_id] = window

        if window.request_count >= RATE_LIMIT_MAX_REQUESTS:
            retry_after = max(
                1,
                ceil(RATE_LIMIT_WINDOW_SECONDS - (now - window.started_at)),
            )
            return False, 0, retry_after

        window.request_count += 1
        remaining = RATE_LIMIT_MAX_REQUESTS - window.request_count
        return True, remaining, 0


@router.post("/rate-limit", response_model=RateLimitExperimentReceipt)
def run_rate_limit_experiment(
    request: RateLimitExperimentRequest,
    _authorization: ResilienceLabAuthorization,
) -> RateLimitExperimentReceipt:
    allowed, remaining, retry_after = consume_rate_limit(request.client_id)
    if not allowed:
        RESILIENCE_REQUESTS.labels(
            strategy="rate_limit",
            outcome="rate_limited",
        ).inc()
        RESILIENCE_CONTROL_EVENTS.labels(
            strategy="rate_limit",
            event="rate_limited",
        ).inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    RESILIENCE_REQUESTS.labels(
        strategy="rate_limit",
        outcome="allowed",
    ).inc()
    return RateLimitExperimentReceipt(
        limit=RATE_LIMIT_MAX_REQUESTS,
        remaining=remaining,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )


@router.post("/degradation", response_model=DegradationExperimentReceipt)
def run_degradation_experiment(
    request: DegradationExperimentRequest,
    _authorization: ResilienceLabAuthorization,
) -> DegradationExperimentReceipt:
    if request.dependency_available:
        RESILIENCE_REQUESTS.labels(
            strategy="graceful_degradation",
            outcome="normal",
        ).inc()
        return DegradationExperimentReceipt(
            outcome="normal",
            response_source="dependency",
        )

    RESILIENCE_REQUESTS.labels(
        strategy="graceful_degradation",
        outcome="degraded",
    ).inc()
    RESILIENCE_CONTROL_EVENTS.labels(
        strategy="graceful_degradation",
        event="fallback",
    ).inc()
    return DegradationExperimentReceipt(
        outcome="degraded",
        response_source="fallback",
    )
