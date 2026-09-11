import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SLOPolicy(Base):
    __tablename__ = "slo_policies"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "name",
            name="uq_slo_policies_service_name",
        ),
        CheckConstraint(
            "sli_type IN ('availability', 'latency_compliance')",
            name="ck_slo_policies_sli_type",
        ),
        CheckConstraint(
            "objective_percent > 0 AND objective_percent < 100",
            name="ck_slo_policies_objective",
        ),
        CheckConstraint(
            "window_minutes > 0",
            name="ck_slo_policies_window",
        ),
        Index(
            "ix_slo_policies_service_active",
            "service_id",
            "active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sli_type: Mapped[str] = mapped_column(String(40), nullable=False)
    objective_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3),
        nullable=False,
    )
    window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SLOEvaluationRecord(Base):
    __tablename__ = "slo_evaluation_records"
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "sample_key",
            name="uq_slo_evaluations_policy_sample",
        ),
        CheckConstraint(
            "achieved_percent >= 0 AND achieved_percent <= 100",
            name="ck_slo_evaluations_achieved",
        ),
        CheckConstraint(
            "observed_bad_event_count >= 0",
            name="ck_slo_evaluations_bad_events",
        ),
        CheckConstraint(
            "burn_rate >= 0",
            name="ck_slo_evaluations_burn_rate",
        ),
        Index(
            "ix_slo_evaluations_policy_time",
            "policy_id",
            "evaluated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("slo_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    sample_key: Mapped[str] = mapped_column(String(100), nullable=False)
    achieved_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )
    observed_bad_event_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    allowed_bad_event_count: Mapped[Decimal] = mapped_column(
        Numeric(20, 6),
        nullable=False,
    )
    error_budget_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )
    remaining_error_budget_percent: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
    )
    error_budget_consumption_percent: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
    )
    burn_rate: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
    )
    breached: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allowed_downtime_minutes: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6),
        nullable=True,
    )
    observed_downtime_minutes: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6),
        nullable=True,
    )
    sla_impact_minutes: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 6),
        nullable=True,
    )
    raw_sample: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
