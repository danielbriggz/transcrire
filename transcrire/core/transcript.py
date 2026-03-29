# ============================================================
# Transcrire — Transcript Core Logic
# ============================================================
# Pure functions for transcript formatting, timestamp
# offsetting, and chunk stitching.
# No I/O — takes strings/lists, returns strings.
#
# Usage:
#   from transcrire.core.transcript import stitch_transcripts
# ============================================================

from __future__ import annotations

import re
from datetime import timedelta

from transcrire.domain.enums import TranscriptType


# ============================================================
# TIMESTAMP HELPERS
# ============================================================

def seconds_to_timestamp(seconds: float) -> str:
    """Converts a float seconds value to HH:MM:SS string."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02}:{m:02}:{s:02}"


def timestamp_to_seconds(ts: str) -> int:
    """Converts a HH:MM:SS string to total seconds (int)."""
    parts = ts.strip().split(":")
    if len(parts) != 3:
        return 0
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s


def offset_timestamp(ts: str, offset_seconds: int) -> str:
    """
    Adds offset_seconds to a HH:MM:SS timestamp string.
    Uses timedelta for correct arithmetic — no string manipulation.

    Args:
        ts:             HH:MM:SS timestamp string.
        offset_seconds: Number of seconds to add.

    Returns:
        Adjusted HH:MM:SS string.
    """
    total   = timestamp_to_seconds(ts) + offset_seconds
    delta   = timedelta(seconds=total)
    hours   = int(delta.total_seconds()) // 3600
    minutes = (int(delta.total_seconds()) % 3600) // 60
    secs    = int(delta.total_seconds()) % 60
    return f"{hours:02}:{minutes:02}:{secs:02}"


# ============================================================
# SEGMENT LINE OFFSETTING
# ============================================================

_SEGMENT_PATTERN = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}) - (\d{2}:\d{2}:\d{2})\](.*)"
)

_WORD_TS_PATTERN = re.compile(r"\[(\d{2}:\d{2}:\d{2})\]")


def offset_segment_line(line: str, offset_seconds: int) -> str:
    """
    Adjusts timestamps in a single segment-level transcript line.
    Format: [HH:MM:SS - HH:MM:SS] text

    Returns the adjusted line, or the original if parsing fails.
    """
    match = _SEGMENT_PATTERN.match(line)
    if not match:
        return line

    start_str, end_str, text = match.groups()
    start_adj = offset_timestamp(start_str, offset_seconds)
    end_adj   = offset_timestamp(end_str,   offset_seconds)
    return f"[{start_adj} - {end_adj}]{text}"


def offset_word_line(transcript: str, offset_seconds: int) -> str:
    """
    Adjusts all timestamps in a word-level transcript string.
    Format: [HH:MM:SS] word [HH:MM:SS] word ...

    Returns the adjusted transcript string.
    """
    def replace_ts(match: re.Match) -> str:
        return "[" + offset_timestamp(match.group(1), offset_seconds) + "]"

    return _WORD_TS_PATTERN.sub(replace_ts, transcript)


# ============================================================
# STITCHING
# ============================================================

def stitch_transcripts(
    transcripts: list[str],
    transcript_type: TranscriptType,
    chunk_seconds: int = 300,
) -> str:
    """
    Joins chunk transcripts into a single coherent output.
    Adjusts timestamps for segment and word-level types so the
    final transcript is accurate to the full audio file.

    Args:
        transcripts:     Ordered list of per-chunk transcript strings.
        transcript_type: Determines how timestamps are offset.
        chunk_seconds:   Duration of each chunk. Default 300 (5 min).

    Returns:
        Single stitched transcript string.
    """
    if transcript_type == TranscriptType.PLAIN:
        return " ".join(t.strip() for t in transcripts if t)

    elif transcript_type == TranscriptType.SEGMENTS:
        lines = []
        for chunk_index, transcript in enumerate(transcripts):
            if not transcript:
                continue
            offset = chunk_index * chunk_seconds
            for line in transcript.strip().splitlines():
                line = line.strip()
                if line:
                    lines.append(offset_segment_line(line, offset))
        return "\n".join(lines)

    elif transcript_type == TranscriptType.WORDS:
        parts = []
        for chunk_index, transcript in enumerate(transcripts):
            if not transcript:
                continue
            offset = chunk_index * chunk_seconds
            parts.append(offset_word_line(transcript, offset))
        return " ".join(parts)

    # Fallback
    return " ".join(t.strip() for t in transcripts if t)
