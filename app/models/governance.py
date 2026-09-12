import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReleaseRecommendation(Base):
    __tablename__ = "release_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            name="uq_release_recommendations_observation",
        ),
        CheckConstraint(
            "decision IN ('proceed', 'manual_review', 'block')",
            name="ck_release_recommendations_decision",
        ),
        CheckConstraint(
            "automated_mutation_allowed = false",
            name="ck_release_recommendations_no_mutation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_observations.id", ondelete="CASCADE"),
        nullable=False,
    )
    release_status: Mapped[str] = mapped_column(String(30), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_budget_burn_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6),
        nullable=True,
    )
    slo_breached: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    human_approval_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    automated_mutation_allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReleaseApproval(Base):
    __tablename__ = "release_approvals"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            name="uq_release_approvals_recommendation",
        ),
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_release_approvals_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_recommendations.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
