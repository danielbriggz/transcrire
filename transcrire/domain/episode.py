# ============================================================
# Transcrire — Episode Domain Object
# ============================================================
# Represents a single podcast episode being processed.
# Maps directly to a row in the episodes table.
#
# Crucially: episode state is DERIVED from stage_results,
# never stored as a column. derive_state() and
# completion_level() are the single source of truth.
#
# Usage:
#   from transcrire.domain.episode import Episode
# ============================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from transcrire.domain.enums import (
    CompletionLevel,
    EpisodeState,
    Stage,
    Status,
)
from transcrire.domain.stage_result import StageResult


@dataclass
class Episode:
    """
    A single podcast episode and its associated pipeline state.

    Attributes:
        podcast_name  : Name of the podcast (matches feeds table).
        season        : Season number.
        episode       : Episode number.
        title         : Full episode title from RSS feed.
        safe_title    : Filesystem-safe version of title.
        spotify_link  : Episode link from RSS feed.
        folder_path   : Absolute path to the episode output folder.
                        Updated by transcrire recover if folder is moved.
        stage_results : All stage execution records for this episode.
                        Populated by storage/db.py when loading.
        created_at    : When this episode was first created.
        updated_at    : When this episode was last modified.
        id            : Database row ID. None until persisted.
    """

    podcast_name  : str
    season        : int
    episode       : int
    title         : str                  = ""
    safe_title    : str                  = ""
    spotify_link  : str | None           = None
    folder_path   : Path | None          = None
    stage_results : list[StageResult]    = field(default_factory=list)
    created_at    : datetime             = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at    : datetime             = field(default_factory=lambda: datetime.now(timezone.utc))
    id            : int | None           = None

    # ----------------------------------------------------------
    # Derived state — never stored in the database
    # ----------------------------------------------------------

    def derive_state(self) -> EpisodeState:
        """
        Derives the current episode state from stage_results.

        Rules (in priority order):
          1. Any FAILED stage → ERROR
          2. IMAGES COMPLETED → IMAGES_GENERATED
          3. CAPTIONS COMPLETED → CAPTIONS_GENERATED
          4. TRANSCRIBE COMPLETED → TRANSCRIBED
          5. FETCH COMPLETED → FETCHED
          6. Otherwise → CREATED

        This is the single source of truth for episode state.
        Never call this from the CLI directly — use
        pipeline.get_available_actions() instead.
        """
        if any(r.status == Status.FAILED for r in self.stage_results):
            return EpisodeState.ERROR

        completed = {
            r.stage
            for r in self.stage_results
            if r.status == Status.COMPLETED
        }

        if Stage.IMAGES in completed:
            return EpisodeState.IMAGES_GENERATED
        if Stage.CAPTIONS in completed:
            return EpisodeState.CAPTIONS_GENERATED
        if Stage.TRANSCRIBE in completed:
            return EpisodeState.TRANSCRIBED
        if Stage.FETCH in completed:
            return EpisodeState.FETCHED
        return EpisodeState.CREATED

    def completion_level(self) -> CompletionLevel:
        """
        Returns the tiered completion level of this episode.

        Replaces binary pass/fail — a pipeline that completes
        transcription but fails at captions is BASIC, not FAILED.

        FULL       : transcript + captions + images
        ENHANCED   : transcript + captions
        BASIC      : transcript only
        INCOMPLETE : nothing completed yet
        """
        state = self.derive_state()

        if state == EpisodeState.IMAGES_GENERATED:
            return CompletionLevel.FULL
        if state == EpisodeState.CAPTIONS_GENERATED:
            return CompletionLevel.ENHANCED
        if state == EpisodeState.TRANSCRIBED:
            return CompletionLevel.BASIC
        return CompletionLevel.INCOMPLETE

    # ----------------------------------------------------------
    # Convenience properties
    # ----------------------------------------------------------

    @property
    def has_error(self) -> bool:
        return self.derive_state() == EpisodeState.ERROR

    @property
    def last_failed_stage(self) -> StageResult | None:
        """Returns the most recent FAILED stage result, if any."""
        failed = [r for r in self.stage_results if r.failed]
        return failed[-1] if failed else None

    @property
    def last_completed_stage(self) -> StageResult | None:
        """Returns the most recent COMPLETED stage result, if any."""
        completed = [r for r in self.stage_results if r.succeeded]
        return completed[-1] if completed else None

    @property
    def pending_review(self) -> list[StageResult]:
        """Returns all stage results that need user review."""
        return [r for r in self.stage_results if r.needs_review]

    @property
    def identifier(self) -> str:
        """Human-readable episode identifier for display and logging."""
        return f"S{self.season}E{self.episode}"

    def stage_result_for(self, stage: Stage) -> StageResult | None:
        """Returns the most recent result for the given stage, if any."""
        results = [r for r in self.stage_results if r.stage == stage]
        return results[-1] if results else None
