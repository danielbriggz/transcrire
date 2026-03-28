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
