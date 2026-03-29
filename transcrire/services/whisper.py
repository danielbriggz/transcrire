# ============================================================
# Transcrire — Whisper Transcription Service
# ============================================================
# Offline transcription via OpenAI Whisper (small model).
# Includes chunk-level checkpoint support for long files.
#
# Chunk-level checkpointing is used ONLY for offline Whisper
# because transcription of a 60-90 minute episode can take
# 20-40 minutes. Groq is fast enough that stage-level restart
# is acceptable.
#
# Checkpoint state is stored in the setup table keyed by
# the audio file's path hash — replaces the old
# transcription_checkpoint.json file.
#
# Usage:
#   from transcrire.services.whisper import transcribe_whisper
# ============================================================

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from transcrire.config import settings
from transcrire.domain.enums import TranscriptType
from transcrire.events import emit
from transcrire.services.audio import CHUNK_SECONDS, split

logger = logging.getLogger(__name__)

# Setup table key prefix for transcription checkpoints
_CHECKPOINT_PREFIX = "checkpoint:"


# ============================================================
# EXCEPTIONS
# ============================================================

class WhisperError(Exception):
    """Raised when a Whisper transcription fails."""


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def transcribe_whisper(
    audio_path: Path,
    transcript_type: TranscriptType,
    episode_id: int | None = None,
) -> str:
    """
    Transcribes audio using local Whisper (small model).

    For files over CHUNK_SECONDS (5 min), uses chunk-level
    transcription with checkpoint saving after each chunk.
    For shorter files, transcribes in a single pass.

    Args:
        audio_path:      Path to the audio file.
        transcript_type: Output format — plain, segments or words.
        episode_id:      Used for checkpoint event emission. Optional.

    Returns:
        Transcript string in the requested format.

    Raises:
        WhisperError on transcription failure.
    """
    from transcrire.services.audio import get_duration

    try:
        duration = get_duration(audio_path)
    except Exception:
        # If duration check fails, default to chunked to be safe
        duration = CHUNK_SECONDS + 1

    if duration > CHUNK_SECONDS:
        logger.info(
            "Audio exceeds chunk threshold — using chunked transcription",
            extra={"duration_s": round(duration), "file": audio_path.name},
        )
        return _transcribe_chunked(audio_path, transcript_type, episode_id)
    else:
        return _transcribe_single(audio_path, transcript_type)


# ============================================================
# SINGLE-PASS TRANSCRIPTION
# ============================================================

def _transcribe_single(audio_path: Path, transcript_type: TranscriptType) -> str:
    """Transcribes a short audio file in a single Whisper pass."""
    logger.info(
        "Starting single-pass Whisper transcription",
        extra={"file": audio_path.name, "type": transcript_type.value},
    )

    try:
        import whisper
        model = whisper.load_model("small")

        if transcript_type == TranscriptType.WORDS:
            result = model.transcribe(str(audio_path), word_timestamps=True)
            words  = [w for seg in result["segments"] for w in seg.get("words", [])]
            return _format_words(words)

        elif transcript_type == TranscriptType.SEGMENTS:
            result = model.transcribe(str(audio_path))
            return _format_segments(result["segments"])

        else:
            result = model.transcribe(str(audio_path))
            return result["text"]

    except FileNotFoundError as e:
        raise WhisperError(f"Audio file not found: {audio_path}") from e
    except Exception as e:
        raise WhisperError(f"Whisper transcription failed: {e}") from e


# ============================================================
# CHUNKED TRANSCRIPTION WITH CHECKPOINT
# ============================================================

def _transcribe_chunked(
    audio_path: Path,
    transcript_type: TranscriptType,
    episode_id: int | None,
) -> str:
    """
    Transcribes a long audio file in 5-minute chunks.
    Saves progress to the setup table after each chunk.
    Resumes from the last completed chunk if a matching
    checkpoint exists.
    """
    from transcrire.storage.db import Database

    db             = Database()
    checkpoint_key = _checkpoint_key(audio_path, transcript_type)
    checkpoint     = _load_checkpoint(db, checkpoint_key)

    chunks       : list[Path] = []
    transcripts  : list[str]  = []
    resume_index : int        = 0

    # ---- Check for existing checkpoint ----
    if checkpoint:
        if _checkpoint_matches(checkpoint, audio_path, transcript_type):
            resume_index = len(checkpoint.get("completed", []))
            transcripts  = checkpoint.get("transcripts", [])
            chunks       = [Path(p) for p in checkpoint.get("chunks", [])]
            logger.info(
                "Resuming from checkpoint",
                extra={"resume_chunk": resume_index, "total": len(chunks)},
            )
        else:
            # Stale checkpoint — clear it and start fresh
            logger.warning("Stale checkpoint found — clearing and starting fresh")
            _clear_checkpoint(db, checkpoint_key)

    # ---- Split audio if not resuming ----
    if not chunks:
        chunks_dir = settings.output_folder / "chunks"
        chunks = split(audio_path, chunks_dir)

        _save_checkpoint(db, checkpoint_key, {
            "audio_path":      str(audio_path),
            "transcript_type": transcript_type.value,
            "total_chunks":    len(chunks),
            "completed":       [],
            "transcripts":     [],
            "chunks":          [str(c) for c in chunks],
        })

    total = len(chunks)
    logger.info("Chunked transcription started", extra={"total_chunks": total})

    # ---- Transcribe each chunk ----
    for i in range(resume_index, total):
        chunk = chunks[i]
        logger.info(f"Transcribing chunk {i + 1}/{total}", extra={"chunk": chunk.name})

        chunk_transcript = _transcribe_single(chunk, transcript_type)
        transcripts.append(chunk_transcript)

        # Save progress after every chunk
        _save_checkpoint(db, checkpoint_key, {
            "audio_path":      str(audio_path),
            "transcript_type": transcript_type.value,
            "total_chunks":    total,
            "completed":       list(range(i + 1)),
            "transcripts":     transcripts,
            "chunks":          [str(c) for c in chunks],
        })

        if episode_id is not None:
            emit("checkpoint_saved",
                 episode_id=episode_id,
                 chunk_index=i + 1,
                 total_chunks=total)

        logger.info(f"Chunk {i + 1}/{total} complete")

    # ---- Stitch results ----
    final = _stitch(transcripts, transcript_type)

    # ---- Clean up checkpoint and chunks ----
    _clear_checkpoint(db, checkpoint_key)
    _cleanup_chunks(chunks)

    logger.info("Chunked transcription complete")
    return final


# ============================================================
# CHECKPOINT HELPERS
# ============================================================

def _checkpoint_key(audio_path: Path, transcript_type: TranscriptType) -> str:
    """Generates a setup table key for a given transcription job."""
    path_hash = hashlib.md5(str(audio_path).encode()).hexdigest()[:12]
    return f"{_CHECKPOINT_PREFIX}{path_hash}:{transcript_type.value}"


def _load_checkpoint(db, key: str) -> dict | None:
    raw = db.get_setup(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _save_checkpoint(db, key: str, data: dict) -> None:
    db.set_setup(key, json.dumps(data))


def _clear_checkpoint(db, key: str) -> None:
    db.delete_setup(key)
    logger.debug("Checkpoint cleared", extra={"key": key})


def _checkpoint_matches(checkpoint: dict, audio_path: Path, transcript_type: TranscriptType) -> bool:
    return (
        checkpoint.get("audio_path")      == str(audio_path) and
        checkpoint.get("transcript_type") == transcript_type.value
    )


def _cleanup_chunks(chunks: list[Path]) -> None:
    """Deletes chunk files after successful transcription."""
    for chunk in chunks:
        try:
            chunk.unlink(missing_ok=True)
        except Exception:
            pass
    # Remove the chunks directory if empty
    if chunks:
        try:
            chunks[0].parent.rmdir()
        except Exception:
            pass


# ============================================================
# FORMATTERS
# ============================================================

def _format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


def _format_segments(segments: list) -> str:
    lines = []
    for seg in segments:
        start = _format_timestamp(seg.get("start", 0))
        end   = _format_timestamp(seg.get("end",   0))
        text  = seg.get("text", "").strip()
        lines.append(f"[{start} - {end}] {text}")
    return "\n".join(lines)


def _format_words(words: list) -> str:
    parts = []
    for word in words:
        ts   = _format_timestamp(word.get("start", 0))
        text = word.get("word", "").strip()
        parts.append(f"[{ts}] {text}")
    return " ".join(parts)


def _stitch(transcripts: list[str], transcript_type: TranscriptType) -> str:
    """
    Joins chunk transcripts into a single output.
    Offsets timestamps for segment and word-level types
    so the final transcript is accurate to the full audio file.
    """
    from transcrire.core.transcript import stitch_transcripts
    return stitch_transcripts(transcripts, transcript_type)
