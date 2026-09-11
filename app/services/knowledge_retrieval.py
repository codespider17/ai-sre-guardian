import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas_knowledge import (
    KnowledgeHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
)

KNOWLEDGE_CATEGORIES = frozenset(
    {"kubernetes", "prometheus", "deployment", "slo", "security", "capacity"}
)
TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{1,}")
MAX_EXCERPT_CHARACTERS = 300


class KnowledgeRetrievalError(Exception):
    pass


@dataclass(frozen=True)
class KnowledgeSeed:
    document_key: str
    title: str
    category: str
    source_ref: str
    version: str
    content: str
    tags: tuple[str, ...]
    priority: int


DEFAULT_KNOWLEDGE: tuple[KnowledgeSeed, ...] = (
    KnowledgeSeed(
        document_key="kubernetes-rollout-recovery",
        title="Kubernetes rollout and rollback recovery",
        category="kubernetes",
        source_ref="runbook://kubernetes/rollout-recovery",
        version="1.0.0",
        content=(
            "Inspect deployment conditions, ReplicaSet events and pod readiness "
            "before deciding whether a rollout should continue or rollback."
        ),
        tags=("kubernetes", "rollout", "rollback", "readiness", "deployment"),
        priority=90,
    ),
    KnowledgeSeed(
        document_key="prometheus-target-diagnosis",
        title="Prometheus target and alert diagnosis",
        category="prometheus",
        source_ref="runbook://prometheus/target-diagnosis",
        version="1.0.0",
        content=(
            "Validate target health, scrape errors and alert labels before using "
            "metric evidence in an incident conclusion."
        ),
        tags=("prometheus", "target", "scrape", "alert", "metrics"),
        priority=80,
    ),
    KnowledgeSeed(
        document_key="deployment-risk-review",
        title="Deployment change risk review",
        category="deployment",
        source_ref="runbook://deployment/risk-review",
        version="1.0.0",
        content=(
            "Review database migrations, infrastructure changes, image changes "
            "and rollback readiness before approving a high-risk deployment."
        ),
        tags=("deployment", "change", "risk", "migration", "approval"),
        priority=85,
    ),
    KnowledgeSeed(
        document_key="slo-error-budget-response",
        title="SLO error budget and burn-rate response",
        category="slo",
        source_ref="runbook://slo/error-budget-response",
        version="1.0.0",
        content=(
            "Compare availability and latency SLI values with the SLO target, "
            "then calculate error budget consumption and burn rate."
        ),
        tags=("slo", "sli", "availability", "latency", "error-budget", "burn-rate"),
        priority=90,
    ),
    KnowledgeSeed(
        document_key="least-privilege-investigation",
        title="Least privilege incident investigation",
        category="security",
        source_ref="runbook://security/least-privilege",
        version="1.0.0",
        content=(
            "Use namespace allowlists, read-only credentials, bounded logs and "
            "audited tool calls during automated incident investigation."
        ),
        tags=("security", "rbac", "read-only", "allowlist", "audit"),
        priority=95,
    ),
    KnowledgeSeed(
        document_key="capacity-hpa-baseline",
        title="Capacity baseline and HPA validation",
        category="capacity",
        source_ref="runbook://capacity/hpa-baseline",
        version="1.0.0",
        content=(
            "Record k6 throughput, latency, error rate and resource saturation "
            "before validating HPA scale-out and recovery behavior."
        ),
        tags=("capacity", "k6", "hpa", "latency", "saturation", "scale-out"),
        priority=80,
    ),
)


def _terms(value: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(value.lower()))


def _score_hit(
    query_terms: set[str],
    document: KnowledgeDocument,
    chunk: KnowledgeChunk,
) -> tuple[int, list[str]] | None:
    title = document.title.lower()
    content = chunk.content.lower()
    tags = {tag.lower() for tag in chunk.tags}
    matched_terms: list[str] = []
    score = 0
    for term in sorted(query_terms):
        matched = False
        if term in tags:
            score += 10
            matched = True
        if term in title:
            score += 6
            matched = True
        if term in content:
            score += 2
            matched = True
        if matched:
            matched_terms.append(term)
    if not matched_terms:
        return None
    score += chunk.priority // 20
    return score, matched_terms


def seed_default_knowledge(session: Session) -> int:
    for seed in DEFAULT_KNOWLEDGE:
        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.document_key == seed.document_key
            )
        )
        if document is None:
            document = KnowledgeDocument(document_key=seed.document_key)
            session.add(document)
        document.title = seed.title
        document.category = seed.category
        document.source_ref = seed.source_ref
        document.version = seed.version
        document.enabled = True
        session.flush()

        chunk = session.scalar(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id == document.id,
                KnowledgeChunk.chunk_key == "overview",
            )
        )
        if chunk is None:
            chunk = KnowledgeChunk(
                document_id=document.id,
                chunk_key="overview",
            )
            session.add(chunk)
        chunk.content = seed.content
        chunk.tags = list(seed.tags)
        chunk.priority = seed.priority
    session.commit()
    return len(DEFAULT_KNOWLEDGE)


def search_knowledge(
    session: Session,
    request: KnowledgeSearchRequest,
) -> KnowledgeSearchResult:
    unknown_categories = set(request.categories) - KNOWLEDGE_CATEGORIES
    if unknown_categories:
        raise KnowledgeRetrievalError("knowledge category is not allowed")

    query_terms = _terms(request.query)
    if not query_terms:
        return KnowledgeSearchResult(query=request.query, hit_count=0, hits=[])

    statement = (
        select(KnowledgeDocument, KnowledgeChunk)
        .join(
            KnowledgeChunk,
            KnowledgeChunk.document_id == KnowledgeDocument.id,
        )
        .where(KnowledgeDocument.enabled.is_(True))
    )
    if request.categories:
        statement = statement.where(KnowledgeDocument.category.in_(request.categories))

    hits: list[KnowledgeHit] = []
    for document, chunk in session.execute(statement):
        scored = _score_hit(query_terms, document, chunk)
        if scored is None:
            continue
        score, matched_terms = scored
        hits.append(
            KnowledgeHit(
                document_id=document.id,
                chunk_id=chunk.id,
                document_key=document.document_key,
                chunk_key=chunk.chunk_key,
                title=document.title,
                category=document.category,
                source_ref=document.source_ref,
                version=document.version,
                score=score,
                matched_terms=matched_terms,
                excerpt=chunk.content[:MAX_EXCERPT_CHARACTERS],
            )
        )

    hits.sort(key=lambda hit: (-hit.score, hit.document_key, hit.chunk_key))
    selected = hits[: request.limit]
    return KnowledgeSearchResult(
        query=request.query,
        hit_count=len(selected),
        hits=selected,
    )
