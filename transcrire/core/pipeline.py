# ============================================================
# Transcrire — Pipeline Core Logic
# ============================================================
# Orchestrates the pipeline state machine.
# Derives episode state from stage results.
# Returns available actions to the CLI — never decides
# what to render, only what is valid.
#
# Usage:
#   from transcrire.core.pipeline import get_available_actions
# ============================================================

from __future__ import annotations

import logging
from dataclasses import dataclass

from transcrire.domain.enums import EpisodeState, Stage, Status
from transcrire.domain.episode import Episode

logger = logging.getLogger(__name__)


# ============================================================
# ACTIONS
# ============================================================

@dataclass(frozen=True)
class Action:
    """
    Represents a valid action the user can take for an episode.
    The CLI renders these — it never decides them itself.

    Attributes:
        key:         Short identifier used for menu input matching.
        label:       Human-readable label shown in the menu.
        stage:       Pipeline stage this action triggers. None for
                     non-pipeline actions (e.g. view summary).
        is_primary:  True if this is the recommended next step.
    """
    key:        str
    label:      str
    stage:      Stage | None = None
    is_primary: bool         = False


# ============================================================
# AVAILABLE ACTIONS
# State-to-action mapping lives here — never in the CLI.
# ============================================================

def get_available_actions(episode: Episode | None) -> list[Action]:
    """
    Returns the list of valid actions for the current episode state.
    The CLI calls this on every menu render and displays the result.

    Args:
        episode: The current active episode, or None if no episode
                 is loaded yet.

    Returns:
        Ordered list of Action objects. Primary action is always first.
    """
    if episode is None:
        return [
            Action("1", "Start new episode (RSS)",    stage=Stage.FETCH,      is_primary=True),
            Action("2", "Transcribe PC audio",         stage=Stage.TRANSCRIBE, is_primary=False),
        ]

    state = episode.derive_state()

    if state == EpisodeState.ERROR:
        last_failed = episode.last_failed_stage
        stage_label = last_failed.stage.value.title() if last_failed else "last stage"
        return [
            Action("1", f"Retry {stage_label}",       stage=last_failed.stage if last_failed else None, is_primary=True),
            Action("2", "View error details",          stage=None,             is_primary=False),
            Action("3", "Start fresh (new episode)",  stage=Stage.FETCH,      is_primary=False),
        ]

    if state == EpisodeState.CREATED:
        return [
            Action("1", "Fetch episode",              stage=Stage.FETCH,      is_primary=True),
            Action("2", "Start different episode",    stage=Stage.FETCH,      is_primary=False),
        ]

    if state == EpisodeState.FETCHED:
        return [
            Action("1", "Transcribe",                 stage=Stage.TRANSCRIBE, is_primary=True),
            Action("2", "Fetch a different episode",  stage=Stage.FETCH,      is_primary=False),
        ]

    if state == EpisodeState.TRANSCRIBED:
        return [
            Action("1", "Generate captions",          stage=Stage.CAPTIONS,   is_primary=True),
            Action("2", "Review transcript",          stage=None,             is_primary=False),
            Action("3", "Re-transcribe",              stage=Stage.TRANSCRIBE, is_primary=False),
        ]

    if state == EpisodeState.CAPTIONS_GENERATED:
        return [
            Action("1", "Generate images",            stage=Stage.IMAGES,     is_primary=True),
            Action("2", "Review captions",            stage=None,             is_primary=False),
            Action("3", "Re-generate captions",       stage=Stage.CAPTIONS,   is_primary=False),
        ]

    if state == EpisodeState.IMAGES_GENERATED:
        return [
            Action("1", "Review images",              stage=None,             is_primary=True),
            Action("2", "Start new episode",          stage=Stage.FETCH,      is_primary=False),
        ]

    if state == EpisodeState.COMPLETE:
        return [
            Action("1", "Start new episode",          stage=Stage.FETCH,      is_primary=True),
            Action("2", "View episode summary",       stage=None,             is_primary=False),
        ]

    # Fallback — should never reach here
    return [
        Action("1", "Start new episode",              stage=Stage.FETCH,      is_primary=True),
    ]


# ============================================================
# VALIDATION
# ============================================================

def validate_api_keys(gemini_key: str, groq_key: str) -> list[str]:
    """
    Format-checks API keys before a pipeline run.
    Not a live test call — just confirms keys are non-empty
    and not placeholder strings.

    Returns:
        List of warning strings. Empty list means all keys look valid.
    """
    warnings = []
    placeholders = {"your-gemini-api-key-here", "your-groq-api-key-here", ""}

    if not gemini_key or gemini_key.lower() in placeholders:
        warnings.append(
            "GEMINI_API_KEY is missing or appears to be a placeholder. "
            "Caption generation will fail."
        )

    if not groq_key or groq_key.lower() in placeholders:
        warnings.append(
            "GROQ_API_KEY is missing or appears to be a placeholder. "
            "Groq transcription will not be available."
        )

    return warnings


# ============================================================
# STAGE TIMING HELPER
# ============================================================

def format_duration(duration_ms: int | None) -> str:
    """
    Formats a duration in milliseconds to a human-readable string.
    Used in CLI summary display and logging.

    Args:
        duration_ms: Duration in milliseconds, or None.

    Returns:
        Formatted string e.g. "4m 14s" or "38s" or "—"
    """
    if duration_ms is None:
        return "—"

    total_s = duration_ms // 1000
    if total_s >= 60:
        m = total_s // 60
        s = total_s % 60
        return f"{m}m {s}s"
    return f"{total_s}s"
