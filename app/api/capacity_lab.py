from secrets import compare_digest
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

from app.schemas_capacity_lab import CapacityWorkReceipt, CapacityWorkRequest
from app.settings import get_settings

CAPACITY_REQUESTS = Counter(
    "ai_sre_capacity_requests_total",
    "Capacity lab requests grouped by outcome.",
    ("outcome",),
)
CAPACITY_DURATION = Histogram(
    "ai_sre_capacity_request_duration_seconds",
    "Capacity lab request duration in seconds.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
CAPACITY_ACTIVE = Gauge(
    "ai_sre_capacity_active_requests",
    "Capacity lab requests currently executing.",
)

router = APIRouter(
    prefix="/api/v1/capacity-lab",
    tags=["capacity-lab"],
)
metrics_router = APIRouter(tags=["metrics"])


def authorize_capacity_lab(
    token: Annotated[
        str | None,
        Header(alias="X-Capacity-Lab-Token"),
    ] = None,
) -> None:
    expected = get_settings().capacity_lab_token
    if token is None or not compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid capacity lab token",
        )


CapacityLabAuthorization = Annotated[
    None,
    Depends(authorize_capacity_lab),
]


@router.post("/work", response_model=CapacityWorkReceipt)
def run_capacity_work(
    request: CapacityWorkRequest,
    _authorization: CapacityLabAuthorization,
) -> CapacityWorkReceipt:
    started = perf_counter()
    checksum = request.seed
    CAPACITY_ACTIVE.inc()
    try:
        for index in range(request.iterations):
            checksum = (checksum * 33 + index) % 2_147_483_647
        CAPACITY_REQUESTS.labels(outcome="success").inc()
        return CapacityWorkReceipt(
            iterations=request.iterations,
            seed=request.seed,
            checksum=checksum,
            duration_ms=round((perf_counter() - started) * 1000, 4),
        )
    finally:
        CAPACITY_DURATION.observe(perf_counter() - started)
        CAPACITY_ACTIVE.dec()


@metrics_router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> Response:
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
