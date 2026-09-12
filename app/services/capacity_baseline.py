from app.schemas_capacity import (
    CapacityBaselinePolicy,
    CapacityBaselineResult,
    CapacityBaselineSample,
)


def rounded(value: float) -> float:
    return round(value, 4)


def calculate_capacity_baseline(
    sample: CapacityBaselineSample,
    policy: CapacityBaselinePolicy,
) -> CapacityBaselineResult:
    successful_requests = sample.total_requests - sample.failed_requests
    requests_per_second = sample.total_requests / sample.duration_seconds
    successful_rps = successful_requests / sample.duration_seconds
    error_rate_percent = sample.failed_requests / sample.total_requests * 100
    cpu_cores = sample.peak_cpu_millicores / 1000
    memory_gib = sample.peak_memory_mib / 1024

    reasons: list[str] = []
    if requests_per_second < policy.minimum_requests_per_second:
        reasons.append("throughput_below_target")
    if sample.p95_latency_ms > policy.maximum_p95_latency_ms:
        reasons.append("p95_latency_above_target")
    if error_rate_percent > policy.maximum_error_rate_percent:
        reasons.append("error_rate_above_target")
    if sample.peak_cpu_millicores > policy.maximum_cpu_millicores:
        reasons.append("cpu_above_target")
    if sample.peak_memory_mib > policy.maximum_memory_mib:
        reasons.append("memory_above_target")

    return CapacityBaselineResult(
        virtual_users=sample.virtual_users,
        duration_seconds=sample.duration_seconds,
        total_requests=sample.total_requests,
        successful_requests=successful_requests,
        requests_per_second=rounded(requests_per_second),
        successful_requests_per_second=rounded(successful_rps),
        error_rate_percent=rounded(error_rate_percent),
        p95_latency_ms=sample.p95_latency_ms,
        peak_cpu_millicores=sample.peak_cpu_millicores,
        peak_memory_mib=sample.peak_memory_mib,
        requests_per_cpu_core=rounded(requests_per_second / cpu_cores),
        requests_per_memory_gib=rounded(requests_per_second / memory_gib),
        scale_out_ratio=rounded(sample.peak_replicas / sample.initial_replicas),
        passed=not reasons,
        limit_reason_codes=reasons,
        evidence_refs=sample.evidence_refs,
    )
