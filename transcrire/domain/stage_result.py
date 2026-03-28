# ============================================================
# Transcrire — StageResult Domain Object
# ============================================================
# Represents the outcome of a single pipeline stage execution.
# Maps directly to a row in the stage_results table.
#
# Usage:
#   from transcrire.domain.stage_result import StageResult
# ============================================================

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from transcrire.domain.enums import Stage, Status


@dataclass
class StageResult:
    """
    Outcome of a single pipeline stage execution.

    Attributes:
        id          : Database row ID. None until persisted.
        episode_id  : Foreign key to the episodes table.
        stage       : Which pipeline stage this result is for.
        status      : Outcome of the stage execution.
        output_paths: Files produced by this stage.
        error       : Error message if status is FAILED.
        duration_ms : Wall-clock duration of the stage in ms.
        reviewed    : Whether the user has reviewed this output.
                      Replaces the old _pending_review filename suffix.
        created_at  : When this result was recorded.
    """

    episode_id   : int
    stage        : Stage
    status       : Status
    output_paths : list[Path]        = field(default_factory=list)
    error        : str | None        = None
    duration_ms  : int | None        = None
    reviewed     : bool              = False
    created_at   : datetime          = field(default_factory=datetime.utcnow)
    id           : int | None        = None

    # ----------------------------------------------------------
    # Serialisation helpers
    # Used by storage/db.py when reading from / writing to SQLite
    # ----------------------------------------------------------

    def output_paths_json(self) -> str:
        """Serialise output_paths to a JSON string for DB storage."""
        return json.dumps([str(p) for p in self.output_paths])

    @staticmethod
    def output_paths_from_json(raw: str | None) -> list[Path]:
        """Deserialise output_paths from a JSON string."""
        if not raw:
            return []
        return [Path(p) for p in json.loads(raw)]

    # ----------------------------------------------------------
    # Convenience properties
    # ----------------------------------------------------------

    @property
    def succeeded(self) -> bool:
        return self.status == Status.COMPLETED

    @property
    def failed(self) -> bool:
        return self.status == Status.FAILED

    @property
    def needs_review(self) -> bool:
        """
        True if this is a completed captions stage that has not
        yet been reviewed by the user.
        Replaces the old _pending_review filename suffix check.
        """
        from transcrire.domain.enums import Stage
        return (
            self.stage == Stage.CAPTIONS
            and self.status == Status.COMPLETED
            and not self.reviewed
        )
