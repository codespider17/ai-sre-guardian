from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.schemas_tools import ToolName


class ToolExecutionResult(BaseModel):
    call_id: UUID = Field(default_factory=uuid4)
    tool: ToolName
    status: Literal["succeeded"] = "succeeded"
    read_only: Literal[True] = True
    payload: dict[str, Any]
    truncated: bool = False
    duration_ms: int = Field(ge=0)
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
