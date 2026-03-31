# ============================================================
# Tests — core/pipeline.py
# ============================================================
# Tests for state derivation, completion level, and
# available actions. All pure functions — no I/O, no mocking.
# ============================================================

import pytest

from transcrire.core.pipeline import (
    get_available_actions,
    validate_api_keys,
    format_duration,
)
from transcrire.domain.enums import (
    CompletionLevel,
    EpisodeState,
    Stage,
    Status,
)
from transcrire.domain.episode import Episode
from transcrire.domain.stage_result import StageResult


# ============================================================
# FIXTURES
# ============================================================

def make_episode(**kwargs) -> Episode:
    """Creates a minimal Episode for testing."""
    defaults = dict(
        podcast_name="Test Podcast",
        season=1,
        episode=1,
        title="Test Episode",
        safe_title="Test Episode",
    )
    defaults.update(kwargs)
    return Episode(**defaults)


def make_result(stage: Stage, status: Status, episode_id: int = 1) -> StageResult:
    """Creates a minimal StageResult for testing."""
    return StageResult(
        episode_id=episode_id,
        stage=stage,
        status=status,
    )


# ============================================================
# DERIVE STATE TESTS
# ============================================================

class TestDeriveState:

    def test_no_results_returns_created(self):
        ep = make_episode()
        assert ep.derive_state() == EpisodeState.CREATED

    def test_fetch_completed_returns_fetched(self):
        ep = make_episode()
        ep.stage_results = [make_result(Stage.FETCH, Status.COMPLETED)]
        assert ep.derive_state() == EpisodeState.FETCHED

    def test_transcribe_completed_returns_transcribed(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
        ]
        assert ep.derive_state() == EpisodeState.TRANSCRIBED

    def test_captions_completed_returns_captions_generated(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
        ]
        assert ep.derive_state() == EpisodeState.CAPTIONS_GENERATED

    def test_images_completed_returns_images_generated(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
            make_result(Stage.IMAGES,     Status.COMPLETED),
        ]
        assert ep.derive_state() == EpisodeState.IMAGES_GENERATED

    def test_any_failed_returns_error(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.FAILED),
        ]
        assert ep.derive_state() == EpisodeState.ERROR

    def test_error_takes_priority_over_completed_stages(self):
        """ERROR should be returned even if later stages completed."""
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.FAILED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
        ]
        assert ep.derive_state() == EpisodeState.ERROR

    def test_skipped_stage_does_not_advance_state(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.SKIPPED),
        ]
        # SKIPPED does not count as COMPLETED — state stays FETCHED
        assert ep.derive_state() == EpisodeState.FETCHED

    def test_images_state_without_intermediate_stages(self):
        """
        If only IMAGES is COMPLETED (unusual but possible via recover),
        state should still reflect the highest completed stage.
        """
        ep = make_episode()
        ep.stage_results = [make_result(Stage.IMAGES, Status.COMPLETED)]
        assert ep.derive_state() == EpisodeState.IMAGES_GENERATED


# ============================================================
# COMPLETION LEVEL TESTS
# ============================================================

class TestCompletionLevel:

    def test_no_stages_returns_incomplete(self):
        ep = make_episode()
        assert ep.completion_level() == CompletionLevel.INCOMPLETE

    def test_transcribed_returns_basic(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
        ]
        assert ep.completion_level() == CompletionLevel.BASIC

    def test_captions_returns_enhanced(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
        ]
        assert ep.completion_level() == CompletionLevel.ENHANCED

    def test_images_returns_full(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
            make_result(Stage.IMAGES,     Status.COMPLETED),
        ]
        assert ep.completion_level() == CompletionLevel.FULL

    def test_error_state_returns_incomplete(self):
        """A failed pipeline should not claim a completion level."""
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.FAILED),
        ]
        assert ep.completion_level() == CompletionLevel.INCOMPLETE


# ============================================================
# AVAILABLE ACTIONS TESTS
# ============================================================

class TestGetAvailableActions:

    def test_no_episode_returns_start_options(self):
        actions = get_available_actions(None)
        keys = [a.key for a in actions]
        assert "1" in keys
        assert "2" in keys
        # Primary action should be start new episode
        primary = next(a for a in actions if a.is_primary)
        assert primary.stage == Stage.FETCH

    def test_fetched_episode_offers_transcribe(self):
        ep = make_episode()
        ep.stage_results = [make_result(Stage.FETCH, Status.COMPLETED)]
        actions = get_available_actions(ep)
        primary = next(a for a in actions if a.is_primary)
        assert primary.stage == Stage.TRANSCRIBE

    def test_transcribed_episode_offers_captions(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
        ]
        actions = get_available_actions(ep)
        primary = next(a for a in actions if a.is_primary)
        assert primary.stage == Stage.CAPTIONS

    def test_captions_generated_offers_images(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.COMPLETED),
            make_result(Stage.CAPTIONS,   Status.COMPLETED),
        ]
        actions = get_available_actions(ep)
        primary = next(a for a in actions if a.is_primary)
        assert primary.stage == Stage.IMAGES

    def test_error_state_offers_retry(self):
        ep = make_episode()
        ep.stage_results = [
            make_result(Stage.FETCH,      Status.COMPLETED),
            make_result(Stage.TRANSCRIBE, Status.FAILED),
        ]
        actions = get_available_actions(ep)
        primary = next(a for a in actions if a.is_primary)
        # Primary action should retry the failed stage
        assert primary.stage == Stage.TRANSCRIBE

    def test_all_actions_have_unique_keys(self):
        """No two actions should share the same key."""
        for episode_state_results in [
            [],
            [make_result(Stage.FETCH, Status.COMPLETED)],
            [make_result(Stage.FETCH, Status.COMPLETED),
             make_result(Stage.TRANSCRIBE, Status.COMPLETED)],
        ]:
            ep = make_episode()
            ep.stage_results = episode_state_results
            actions = get_available_actions(ep)
            keys = [a.key for a in actions]
            assert len(keys) == len(set(keys)), f"Duplicate keys found: {keys}"

    def test_exactly_one_primary_action(self):
        """There should always be exactly one primary action."""
        ep = make_episode()
        ep.stage_results = [make_result(Stage.FETCH, Status.COMPLETED)]
        actions = get_available_actions(ep)
        primaries = [a for a in actions if a.is_primary]
        assert len(primaries) == 1


# ============================================================
# VALIDATE API KEYS TESTS
# ============================================================

class TestValidateApiKeys:

    def test_empty_keys_return_warnings(self):
        warnings = validate_api_keys("", "")
        assert len(warnings) == 2

    def test_placeholder_keys_return_warnings(self):
        warnings = validate_api_keys(
            "your-gemini-api-key-here",
            "your-groq-api-key-here",
        )
        assert len(warnings) == 2

    def test_valid_looking_keys_return_no_warnings(self):
        warnings = validate_api_keys("AIzaSyABC123valid", "gsk_abc123valid")
        assert len(warnings) == 0

    def test_missing_gemini_only(self):
        warnings = validate_api_keys("", "gsk_abc123valid")
        assert len(warnings) == 1
        assert "GEMINI" in warnings[0]

    def test_missing_groq_only(self):
        warnings = validate_api_keys("AIzaSyABC123valid", "")
        assert len(warnings) == 1
        assert "GROQ" in warnings[0]


# ============================================================
# FORMAT DURATION TESTS
# ============================================================

class TestFormatDuration:

    def test_none_returns_dash(self):
        assert format_duration(None) == "—"

    def test_under_60_seconds(self):
        assert format_duration(38_000) == "38s"

    def test_exactly_60_seconds(self):
        assert format_duration(60_000) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert format_duration(254_000) == "4m 14s"

    def test_zero(self):
        assert format_duration(0) == "0s"
