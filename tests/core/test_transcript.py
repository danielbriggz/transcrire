# ============================================================
# Tests -- core/transcript.py
# ============================================================
# Tests for timestamp conversion, offsetting, and
# chunk stitching across all three transcript types.
# All pure functions -- no I/O, no mocking.
# ============================================================

import pytest

from transcrire.core.transcript import (
    seconds_to_timestamp,
    timestamp_to_seconds,
    offset_timestamp,
    offset_segment_line,
    offset_word_line,
    stitch_transcripts,
)
from transcrire.domain.enums import TranscriptType


class TestSecondsToTimestamp:

    def test_zero(self):
        assert seconds_to_timestamp(0) == "00:00:00"

    def test_seconds_only(self):
        assert seconds_to_timestamp(45) == "00:00:45"

    def test_minutes_and_seconds(self):
        assert seconds_to_timestamp(125) == "00:02:05"

    def test_hours_minutes_seconds(self):
        assert seconds_to_timestamp(3661) == "01:01:01"

    def test_float_is_truncated(self):
        assert seconds_to_timestamp(59.9) == "00:00:59"

    def test_exact_hour(self):
        assert seconds_to_timestamp(3600) == "01:00:00"


class TestTimestampToSeconds:

    def test_zero(self):
        assert timestamp_to_seconds("00:00:00") == 0

    def test_seconds_only(self):
        assert timestamp_to_seconds("00:00:45") == 45

    def test_minutes_and_seconds(self):
        assert timestamp_to_seconds("00:02:05") == 125

    def test_hours_minutes_seconds(self):
        assert timestamp_to_seconds("01:01:01") == 3661

    def test_malformed_returns_zero(self):
        assert timestamp_to_seconds("not-a-timestamp") == 0

    def test_roundtrip(self):
        for seconds in [0, 30, 125, 3661, 7384]:
            assert timestamp_to_seconds(seconds_to_timestamp(seconds)) == seconds


class TestOffsetTimestamp:

    def test_zero_offset(self):
        assert offset_timestamp("00:01:00", 0) == "00:01:00"

    def test_add_seconds(self):
        assert offset_timestamp("00:00:00", 30) == "00:00:30"

    def test_add_one_chunk(self):
        assert offset_timestamp("00:01:00", 300) == "00:06:00"

    def test_rolls_over_minutes(self):
        assert offset_timestamp("00:00:50", 20) == "00:01:10"

    def test_rolls_over_hours(self):
        assert offset_timestamp("00:59:00", 300) == "01:04:00"

    def test_large_offset(self):
        assert offset_timestamp("00:04:30", 900) == "00:19:30"


class TestOffsetSegmentLine:

    def test_valid_segment_line(self):
        line   = "[00:01:00 - 00:01:30] Some spoken text"
        result = offset_segment_line(line, 300)
        assert result == "[00:06:00 - 00:06:30] Some spoken text"

    def test_zero_offset_unchanged(self):
        line = "[00:01:00 - 00:01:30] Some text"
        assert offset_segment_line(line, 0) == line

    def test_malformed_line_returned_unchanged(self):
        line = "This is not a segment line"
        assert offset_segment_line(line, 300) == line

    def test_empty_line_returned_unchanged(self):
        assert offset_segment_line("", 300) == ""

    def test_preserves_text_content(self):
        line   = "[00:00:10 - 00:00:20] Hello, world!"
        result = offset_segment_line(line, 60)
        assert "Hello, world!" in result

    def test_multiple_chunks_offset(self):
        line   = "[00:00:05 - 00:00:10] Word"
        result = offset_segment_line(line, 600)
        assert result == "[00:10:05 - 00:10:10] Word"


class TestOffsetWordLine:

    def test_single_word(self):
        transcript = "[00:00:01] hello"
        result     = offset_word_line(transcript, 300)
        assert result == "[00:05:01] hello"

    def test_multiple_words(self):
        transcript = "[00:00:01] hello [00:00:02] world"
        result     = offset_word_line(transcript, 60)
        assert result == "[00:01:01] hello [00:01:02] world"

    def test_zero_offset_unchanged(self):
        transcript = "[00:00:01] hello [00:00:02] world"
        assert offset_word_line(transcript, 0) == transcript

    def test_no_timestamps_unchanged(self):
        transcript = "plain text with no timestamps"
        assert offset_word_line(transcript, 300) == transcript

    def test_large_offset(self):
        transcript = "[00:04:55] last"
        result     = offset_word_line(transcript, 300)
        assert result == "[00:09:55] last"


class TestStitchTranscripts:

    def test_plain_joins_with_space(self):
        result = stitch_transcripts(
            ["Hello world.", "This is chunk two."],
            TranscriptType.PLAIN,
        )
        assert result == "Hello world. This is chunk two."

    def test_plain_skips_empty_chunks(self):
        result = stitch_transcripts(
            ["Hello.", "", "World."],
            TranscriptType.PLAIN,
        )
        assert result == "Hello. World."

    def test_plain_single_chunk(self):
        result = stitch_transcripts(["Only chunk."], TranscriptType.PLAIN)
        assert result == "Only chunk."

    def test_plain_empty_list(self):
        result = stitch_transcripts([], TranscriptType.PLAIN)
        assert result == ""

    def test_segments_offsets_second_chunk(self):
        chunk1 = "[00:00:05 - 00:00:10] First"
        chunk2 = "[00:00:05 - 00:00:10] Second"
        result = stitch_transcripts(
            [chunk1, chunk2],
            TranscriptType.SEGMENTS,
            chunk_seconds=300,
        )
        lines = result.splitlines()
        assert lines[0] == "[00:00:05 - 00:00:10] First"
        assert lines[1] == "[00:05:05 - 00:05:10] Second"

    def test_segments_third_chunk_offset(self):
        chunk = "[00:00:01 - 00:00:02] Text"
        result = stitch_transcripts(
            [chunk, chunk, chunk],
            TranscriptType.SEGMENTS,
            chunk_seconds=300,
        )
        lines = result.splitlines()
        assert lines[0] == "[00:00:01 - 00:00:02] Text"
        assert lines[1] == "[00:05:01 - 00:05:02] Text"
        assert lines[2] == "[00:10:01 - 00:10:02] Text"

    def test_segments_skips_empty_chunks(self):
        chunk1 = "[00:00:01 - 00:00:02] First"
        result = stitch_transcripts(
            [chunk1, "", chunk1],
            TranscriptType.SEGMENTS,
            chunk_seconds=300,
        )
        lines = [l for l in result.splitlines() if l]
        assert len(lines) == 2

    def test_words_offsets_second_chunk(self):
        chunk1 = "[00:00:01] hello"
        chunk2 = "[00:00:01] world"
        result = stitch_transcripts(
            [chunk1, chunk2],
            TranscriptType.WORDS,
            chunk_seconds=300,
        )
        assert "[00:00:01] hello" in result
        assert "[00:05:01] world" in result

    def test_words_joins_chunks(self):
        chunk1 = "[00:00:01] one"
        chunk2 = "[00:00:01] two"
        result = stitch_transcripts(
            [chunk1, chunk2],
            TranscriptType.WORDS,
            chunk_seconds=60,
        )
        assert "[00:00:01] one" in result
        assert "[00:01:01] two" in result
