"""Domain model tracking which pipeline stage an execution currently occupies.

Unlike the audit log (an immutable append-only history) or WorkUnit.status
(per-unit outcome), Status is a single mutable pointer per execution that
answers "where is this execution right now" without needing to replay the
audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.shared.constants import StageName
from src.shared.types import ExecutionId

_ALLOWED_TRANSITIONS: dict[StageName, tuple[StageName, ...]] = {
    StageName.INGESTED: (StageName.EXPANDED, StageName.FAILED),
    StageName.EXPANDED: (StageName.EXECUTING, StageName.FAILED),
    StageName.EXECUTING: (StageName.COMPLETED, StageName.FAILED),
    StageName.COMPLETED: (),
    # FAILED is a resumable dead end, not a permanent one: retrying the same
    # execution generation in place (as opposed to the recovery scheduler's
    # fresh generation) re-enters EXECUTING directly, since expansion has
    # already happened.
    StageName.FAILED: (StageName.EXECUTING,),
}


@dataclass(slots=True)
class Status:
    execution_id: ExecutionId
    stage: StageName = StageName.INGESTED
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def advance(self, next_stage: StageName) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.stage]
        if next_stage not in allowed:
            raise ValueError(f"Cannot advance from {self.stage} to {next_stage}")
        self.stage = next_stage
        self.updated_at = datetime.now(UTC)

    def is_terminal(self) -> bool:
        return self.stage == StageName.COMPLETED
