# ============================================================
# Transcrire — Groq Transcription Service
# ============================================================
# Fast cloud transcription via Groq's Whisper Large v3 API.
# All API calls use tenacity exponential backoff.
#
# Usage:
#   from transcrire.services.groq import transcribe_groq
# ============================================================

from __future__ import annotations

import logging
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from transcrire.config import settings
from transcrire.domain.enums import TranscriptType
from transcrire.services.audio import compress

logger = logging.getLogger(__name__)

# Groq file size limit in bytes (25MB)
GROQ_MAX_BYTES = 25 * 1024 * 1024


# ============================================================
# EXCEPTIONS
# ============================================================

class GroqError(Exception):
    """Raised when a Groq API call fails after all retries."""


class GroqFileTooLargeError(GroqError):
    """Raised when compressed audio still exceeds Groq's 25MB limit."""


class GroqAuthError(GroqError):
    """Raised when the Groq API key is invalid."""


# ============================================================
# RETRY DECORATOR
# Exponential backoff on rate limit errors.
# Other errors (auth, file size) are raised immediately.
# ============================================================

def _is_rate_limit(exc: BaseException) -> bool:
    return "429" in str(exc) or "rate_limit" in str(exc).lower()


def _groq_retry(func):
    return retry(
        retry=retry_if_exception_type(GroqError) & retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )(func)


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcribe_groq(
    audio_path: Path,
    transcript_type: TranscriptType,
) -> str:
    """
    Transcribes audio via the Groq Whisper Large v3 API.

    Compresses audio to 64kbps mono before upload to stay
    within Groq's 25MB file size limit.

    Args:
        audio_path:      Path to the audio file.
        transcript_type: Output format — plain, segments or words.

    Returns:
        Transcript string in the requested format.

    Raises:
        GroqAuthError:        API key is invalid.
        GroqFileTooLargeError: File exceeds 25MB after compression.
        GroqError:            Any other Groq API failure.
    """
    from groq import Groq

    # ---- Compress before upload ----
    compressed = audio_path.with_suffix("").with_name(
        audio_path.stem + "_compressed.mp3"
    )

    try:
        compress(audio_path, compressed)
    except Exception as e:
        raise GroqError(f"Audio compression failed: {e}") from e

    # ---- Size check ----
    file_size = compressed.stat().st_size
    if file_size > GROQ_MAX_BYTES:
        compressed.unlink(missing_ok=True)
        raise GroqFileTooLargeError(
            f"Compressed file is {file_size / 1024 / 1024:.1f}MB — "
            f"exceeds Groq's 25MB limit. Use offline Whisper instead."
        )

    logger.info(
        "Sending to Groq",
        extra={
            "file": audio_path.name,
            "size_mb": round(file_size / 1024 / 1024, 2),
            "type": transcript_type.value,
        },
    )

    try:
        result = _call_groq(compressed, transcript_type)
    finally:
        compressed.unlink(missing_ok=True)

    return result


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_groq(compressed: Path, transcript_type: TranscriptType) -> str:
    """
    Makes the actual Groq API call with tenacity backoff.
    Separated from transcribe_groq() so retries don't repeat compression.
    """
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)

    try:
        with open(compressed, "rb") as f:

            if transcript_type == TranscriptType.WORDS:
                response = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                )
                return _format_words(response.words or [])

            elif transcript_type == TranscriptType.SEGMENTS:
                response = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
                return _format_segments(response.segments or [])

            else:
                response = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="text",
                )
                return response

    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "invalid_api_key" in err_str:
            raise GroqAuthError(
                "Invalid Groq API key. "
                "Run \'transcrire --check api-keys\' to update it."
            ) from e
        if "413" in err_str:
            raise GroqFileTooLargeError(
                "File too large for Groq even after compression."
            ) from e
        # Re-raise for tenacity to catch and retry
        raise GroqError(f"Groq API error: {e}") from e


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
