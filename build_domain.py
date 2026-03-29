"""
Transcrire — Domain Layer Build Script
========================================
Run from the project root:
    python build_domain.py

Writes:
  - transcrire/domain/enums.py
  - transcrire/domain/episode.py
  - transcrire/domain/stage_result.py

Overwrites existing placeholder files.
"""

from pathlib import Path

ROOT = Path(__file__).parent
DOMAIN = ROOT / "transcrire" / "domain"


# ============================================================
# HELPERS
# ============================================================

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  WRITTEN: {path}")


# ============================================================
# enums.py
# ============================================================

ENUMS_PY = '''\
# ============================================================
# Transcrire — Domain Enums
# ============================================================
# All typed enums used across the codebase.
# Import from here — never use raw strings for these values.
#
# Usage:
#   from transcrire.domain.enums import Stage, Status
# ============================================================

from enum import Enum


class Stage(str, Enum):
    """Pipeline stages in execution order."""
    FETCH      = "FETCH"
    TRANSCRIBE = "TRANSCRIBE"
    CAPTIONS   = "CAPTIONS"
    IMAGES     = "IMAGES"


class Status(str, Enum):
    """Outcome status for a single stage execution."""
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
    SKIPPED   = "SKIPPED"


class EpisodeState(str, Enum):
    """
    Derived state of an episode based on its stage results.
    Never stored in the database — always computed at query time.
    Order reflects pipeline progression.
    """
    CREATED            = "CREATED"
    FETCHED            = "FETCHED"
    TRANSCRIBED        = "TRANSCRIBED"
    CAPTIONS_GENERATED = "CAPTIONS_GENERATED"
    IMAGES_GENERATED   = "IMAGES_GENERATED"
    COMPLETE           = "COMPLETE"
    ERROR              = "ERROR"


class CompletionLevel(str, Enum):
    """
    Tiered completion model.
    Replaces binary pass/fail for pipeline runs.

    INCOMPLETE : No stages completed successfully
    BASIC      : Transcript exists
    ENHANCED   : Transcript + captions exist
    FULL       : Transcript + captions + images exist
    """
    INCOMPLETE = "INCOMPLETE"
    BASIC      = "BASIC"
    ENHANCED   = "ENHANCED"
    FULL       = "FULL"


class TranscribeMode(str, Enum):
    """Transcription backend selection."""
    GROQ    = "groq"
    WHISPER = "whisper"


class TranscriptType(str, Enum):
    """
    Transcript format selection.
    Determines both the Groq/Whisper response format and
    the output filename suffix.
    """
    PLAIN    = "plain"
    SEGMENTS = "segments"
    WORDS    = "words"

    @property
    def filename_suffix(self) -> str:
        """Suffix appended to the transcript filename."""
        return {
            TranscriptType.PLAIN:    "",
            TranscriptType.SEGMENTS: "_segments",
            TranscriptType.WORDS:    "_words",
        }[self]


class FetchChoice(str, Enum):
    """What assets to fetch from the RSS feed."""
    AUDIO    = "audio"
    COVER    = "cover"
    LINK     = "link"
    ALL      = "all"


class FontWeight(str, Enum):
    """
    Font weight selection for quote card generation.
    Selected automatically based on background brightness.
    """
    MEDIUM   = "Medium"
    SEMIBOLD = "SemiBold"
'''


# ============================================================
# stage_result.py
# ============================================================

STAGE_RESULT_PY = '''\
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
'''


# ============================================================
# episode.py
# ============================================================

EPISODE_PY = '''\
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
from datetime import datetime
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
    created_at    : datetime             = field(default_factory=datetime.utcnow)
    updated_at    : datetime             = field(default_factory=datetime.utcnow)
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
'''


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("\n" + "=" * 50)
    print("  Transcrire — Domain Layer")
    print("=" * 50 + "\n")

    write(DOMAIN / "enums.py",        ENUMS_PY)
    write(DOMAIN / "episode.py",      EPISODE_PY)
    write(DOMAIN / "stage_result.py", STAGE_RESULT_PY)

    print("\n" + "=" * 50)
    print("  Domain layer complete.")
    print("=" * 50)
    print("""
Next steps:
  1. Verify no import errors:
         python -c "from transcrire.domain.episode import Episode; print('OK')"

  2. Commit:
         git add -A
         git commit -m "feat: implement domain layer"
         git push origin rebuild
""")


if __name__ == "__main__":
    main()
