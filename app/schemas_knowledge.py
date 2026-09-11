from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    categories: list[str] = Field(default_factory=list, max_length=6)
    limit: int = Field(default=5, ge=1, le=10)


class KnowledgeHit(BaseModel):
    document_id: UUID
    chunk_id: UUID
    document_key: str
    chunk_key: str
    title: str
    category: str
    source_ref: str
    version: str
    score: int
    matched_terms: list[str]
    excerpt: str


class KnowledgeSearchResult(BaseModel):
    query: str
    hit_count: int
    hits: list[KnowledgeHit]
