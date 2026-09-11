from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas_knowledge import KnowledgeSearchRequest
from app.services.knowledge_retrieval import (
    DEFAULT_KNOWLEDGE,
    MAX_EXCERPT_CHARACTERS,
    KnowledgeRetrievalError,
    search_knowledge,
    seed_default_knowledge,
)


def create_document(
    token: str,
    *,
    category: str = "kubernetes",
    enabled: bool = True,
    priority: int = 50,
    content_size: int = 20,
) -> str:
    document_key = f"test-{uuid4().hex}"
    with SessionLocal() as session:
        document = KnowledgeDocument(
            document_key=document_key,
            title=f"Test knowledge {document_key}",
            category=category,
            source_ref=f"test://{document_key}",
            version="test",
            enabled=enabled,
        )
        session.add(document)
        session.flush()
        session.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_key="test-chunk",
                content=f"{token} " + ("x" * content_size),
                tags=[token],
                priority=priority,
            )
        )
        session.commit()
    return document_key


def test_exact_tag_match_is_ranked_first() -> None:
    token = f"exact{uuid4().hex}"
    expected_key = create_document(token, priority=100)
    with SessionLocal() as session:
        result = search_knowledge(
            session,
            KnowledgeSearchRequest(query=token),
        )
    assert result.hits[0].document_key == expected_key
    assert result.hits[0].matched_terms == [token]


def test_category_filter_excludes_other_categories() -> None:
    token = f"category{uuid4().hex}"
    expected_key = create_document(token, category="security")
    create_document(token, category="capacity")
    with SessionLocal() as session:
        result = search_knowledge(
            session,
            KnowledgeSearchRequest(query=token, categories=["security"]),
        )
    assert [hit.document_key for hit in result.hits] == [expected_key]


def test_disabled_document_is_not_returned() -> None:
    token = f"disabled{uuid4().hex}"
    create_document(token, enabled=False)
    with SessionLocal() as session:
        result = search_knowledge(
            session,
            KnowledgeSearchRequest(query=token),
        )
    assert result.hit_count == 0


def test_result_limit_is_enforced() -> None:
    token = f"limit{uuid4().hex}"
    for _ in range(3):
        create_document(token)
    with SessionLocal() as session:
        result = search_knowledge(
            session,
            KnowledgeSearchRequest(query=token, limit=2),
        )
    assert result.hit_count == 2


def test_excerpt_is_bounded() -> None:
    token = f"excerpt{uuid4().hex}"
    create_document(token, content_size=500)
    with SessionLocal() as session:
        result = search_knowledge(
            session,
            KnowledgeSearchRequest(query=token),
        )
    assert len(result.hits[0].excerpt) == MAX_EXCERPT_CHARACTERS


def test_unknown_category_is_rejected() -> None:
    with SessionLocal() as session, pytest.raises(KnowledgeRetrievalError):
        search_knowledge(
            session,
            KnowledgeSearchRequest(query="rollout", categories=["unknown"]),
        )


def test_default_seed_is_idempotent() -> None:
    default_keys = [seed.document_key for seed in DEFAULT_KNOWLEDGE]
    with SessionLocal() as session:
        assert seed_default_knowledge(session) == 6
        assert seed_default_knowledge(session) == 6
        document_count = session.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.document_key.in_(default_keys))
        )
        chunk_count = session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.document_key.in_(default_keys))
        )
    assert document_count == 6
    assert chunk_count == 6


def test_search_request_limit_boundary() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSearchRequest(query="rollout", limit=11)
