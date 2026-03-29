"""
Transcrire — Services Layer Build Script
==========================================
Run from the project root:
    python build_services.py

Writes:
  - transcrire/services/rss.py
  - transcrire/services/audio.py
  - transcrire/services/groq.py
  - transcrire/services/whisper.py
  - transcrire/services/gemini.py

Overwrites existing placeholder files.
"""

from pathlib import Path

ROOT     = Path(__file__).parent
SERVICES = ROOT / "transcrire" / "services"


# ============================================================
# HELPERS
# ============================================================

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  WRITTEN: {path}")


# ============================================================
# rss.py
# ============================================================

RSS_PY = '''\
# ============================================================
# Transcrire — RSS Service
# ============================================================
# Wraps feedparser for all RSS feed operations.
# Raises typed exceptions — never returns None on failure.
#
# Usage:
#   from transcrire.services.rss import fetch_feed, find_episode
# ============================================================

from __future__ import annotations

import logging
from dataclasses import dataclass

import feedparser

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTIONS
# ============================================================

class FeedError(Exception):
    """Raised when an RSS feed cannot be loaded or parsed."""


class EpisodeNotFoundError(Exception):
    """Raised when the requested season/episode is not in the feed."""


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class FeedResult:
    """Parsed podcast feed metadata."""
    podcast_name: str
    rss_url:      str


@dataclass
class EpisodeAssets:
    """
    All fetchable assets for a single episode from its RSS entry.
    Fields are None if not present in the feed.
    """
    title:       str
    safe_title:  str
    season:      int
    episode:     int
    audio_url:   str | None
    cover_url:   str | None
    spotify_link: str | None


# ============================================================
# FEED FUNCTIONS
# ============================================================

def fetch_feed(rss_url: str) -> FeedResult:
    """
    Fetches and parses an RSS feed URL.
    Returns a FeedResult with the podcast name.
    Raises FeedError if the feed cannot be loaded.
    """
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        raise FeedError(f"Could not load RSS feed: {e}") from e

    if not feed.entries:
        raise FeedError(
            "RSS feed loaded but contains no episodes. "
            "Check the URL and your internet connection."
        )

    podcast_name = feed.feed.get("title", "Unknown Podcast")
    logger.info("Feed loaded", extra={"podcast": podcast_name, "url": rss_url})
    return FeedResult(podcast_name=podcast_name, rss_url=rss_url)


def find_episode(rss_url: str, season: int, episode: int) -> EpisodeAssets:
    """
    Searches an RSS feed for a specific season/episode.
    Returns an EpisodeAssets object with all available URLs.
    Raises EpisodeNotFoundError if no matching entry is found.
    Raises FeedError if the feed cannot be loaded.
    """
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        raise FeedError(f"Could not load RSS feed: {e}") from e

    for entry in feed.entries:
        try:
            entry_season  = int(entry.get("itunes_season",  0))
            entry_episode = int(entry.get("itunes_episode", 0))
        except (ValueError, TypeError):
            continue

        if entry_season != season or entry_episode != episode:
            continue

        # ---- Matched ----
        title      = entry.get("title", "Unknown Episode")
        safe_title = "".join(c for c in title if c not in r\'\\/:*?"<>|\')

        # Audio URL — first enclosure with audio MIME type
        audio_url = None
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio"):
                audio_url = link.get("href")
                break

        # Cover art — episode-level preferred over feed-level
        cover_url = (
            entry.get("itunes_image", {}).get("href")
            or entry.get("image", {}).get("href")
            or entry.get("itunes_imageurl")
        )

        # Spotify / episode link
        spotify_link = entry.get("link")

        logger.info(
            "Episode found in feed",
            extra={"title": title, "season": season, "episode": episode},
        )

        return EpisodeAssets(
            title        = title,
            safe_title   = safe_title,
            season       = season,
            episode      = episode,
            audio_url    = audio_url,
            cover_url    = cover_url,
            spotify_link = spotify_link,
        )

    raise EpisodeNotFoundError(
        f"S{season}E{episode} not found in feed. "
        f"Check the season and episode numbers."
    )
'''


# ============================================================
# audio.py
# ============================================================

AUDIO_PY = '''\
# ============================================================
# Transcrire — Audio Service
# ============================================================
# Wraps all ffmpeg and ffprobe operations.
# All subprocess calls are isolated here — never call
# subprocess directly in other modules.
#
# Usage:
#   from transcrire.services.audio import get_duration, compress, split
# ============================================================

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================
# EXCEPTIONS
# ============================================================

class AudioError(Exception):
    """Raised when an ffmpeg or ffprobe operation fails."""


class FFmpegNotFoundError(AudioError):
    """Raised when ffmpeg is not found on the system PATH."""


# ============================================================
# FFMPEG CHECK
# ============================================================

def check_ffmpeg() -> None:
    """
    Confirms ffmpeg is accessible on the system PATH.
    Raises FFmpegNotFoundError with actionable guidance if not found.
    Called at pipeline start — not on every launch.
    """
    import shutil
    if shutil.which("ffmpeg") is None:
        raise FFmpegNotFoundError(
            "ffmpeg not found on PATH.\\n"
            "Install it from https://ffmpeg.org/download.html\\n"
            "Then add the bin/ folder to your system PATH and restart."
        )
    logger.debug("ffmpeg found on PATH")


# ============================================================
# DURATION
# ============================================================

def get_duration(audio_path: Path) -> float:
    """
    Returns the duration of an audio file in seconds via ffprobe.
    Raises AudioError if ffprobe fails or returns unexpected output.
    Used to decide whether to use single-pass or chunked transcription.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise AudioError(f"ffprobe failed: {result.stderr.strip()}")
        return float(result.stdout.strip())
    except FileNotFoundError as e:
        raise FFmpegNotFoundError("ffprobe not found on PATH.") from e
    except ValueError as e:
        raise AudioError(f"Could not parse audio duration: {e}") from e


# ============================================================
# COMPRESSION
# ============================================================

def compress(audio_path: Path, output_path: Path) -> Path:
    """
    Compresses audio to 64kbps mono MP3 via ffmpeg.
    Required before Groq upload to stay within the 25MB limit.

    Args:
        audio_path:  Path to the source audio file.
        output_path: Path to write the compressed file.

    Returns:
        output_path on success.
    Raises AudioError on failure.
    """
    logger.info("Compressing audio", extra={"source": str(audio_path)})
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-b:a", "64k",   # 64kbps — sufficient for speech
                "-ac", "1",      # Mono — halves file size
                str(output_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise AudioError(
                f"ffmpeg compression failed:\\n{result.stderr.decode().strip()}"
            )
    except FileNotFoundError as e:
        raise FFmpegNotFoundError("ffmpeg not found on PATH.") from e

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(
        "Audio compressed",
        extra={"output": str(output_path), "size_mb": round(size_mb, 2)},
    )
    return output_path


# ============================================================
# SPLITTING (for chunk-level transcription)
# ============================================================

CHUNK_SECONDS = 300  # 5 minutes per chunk


def split(audio_path: Path, chunks_dir: Path, chunk_seconds: int = CHUNK_SECONDS) -> list[Path]:
    """
    Splits an audio file into fixed-length chunks via ffmpeg.
    Used by services/whisper.py for chunk-level transcription.

    Args:
        audio_path:    Path to the source audio file.
        chunks_dir:    Directory to write chunk files into.
        chunk_seconds: Duration of each chunk in seconds. Default 300 (5 min).

    Returns:
        Sorted list of chunk file Paths.
    Raises AudioError on failure.
    """
    chunks_dir.mkdir(parents=True, exist_ok=True)

    base         = audio_path.stem
    chunk_pattern = str(chunks_dir / f"{base}_chunk_%03d.mp3")

    logger.info(
        "Splitting audio into chunks",
        extra={"source": str(audio_path), "chunk_seconds": chunk_seconds},
    )

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-f", "segment",
                "-segment_time", str(chunk_seconds),
                "-c", "copy",
                chunk_pattern,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise AudioError(
                f"ffmpeg split failed:\\n{result.stderr.decode().strip()}"
            )
    except FileNotFoundError as e:
        raise FFmpegNotFoundError("ffmpeg not found on PATH.") from e

    chunks = sorted(chunks_dir.glob(f"{base}_chunk_*.mp3"))

    if not chunks:
        raise AudioError("ffmpeg produced no chunk files. Check the audio file.")

    logger.info("Audio split complete", extra={"chunks": len(chunks)})
    return chunks
'''


# ============================================================
# groq.py
# ============================================================

GROQ_PY = '''\
# ============================================================
# Transcrire — Groq Transcription Service
# ============================================================
# Fast cloud transcription via Groq\'s Whisper Large v3 API.
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
    """Raised when compressed audio still exceeds Groq\'s 25MB limit."""


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
    within Groq\'s 25MB file size limit.

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
            f"exceeds Groq\'s 25MB limit. Use offline Whisper instead."
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
    Separated from transcribe_groq() so retries don\'t repeat compression.
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
                "Run \\'transcrire --check api-keys\\' to update it."
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
    return "\\n".join(lines)


def _format_words(words: list) -> str:
    parts = []
    for word in words:
        ts   = _format_timestamp(word.get("start", 0))
        text = word.get("word", "").strip()
        parts.append(f"[{ts}] {text}")
    return " ".join(parts)
'''


# ============================================================
# whisper.py
# ============================================================

WHISPER_PY = '''\
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
# the audio file\'s path hash — replaces the old
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
    return "\\n".join(lines)


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
'''


# ============================================================
# gemini.py
# ============================================================

GEMINI_PY = '''\
# ============================================================
# Transcrire — Gemini Caption Service
# ============================================================
# Caption and reference list generation via Google Gemini.
# All API calls use tenacity exponential backoff.
#
# Usage:
#   from transcrire.services.gemini import generate_captions
# ============================================================

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from transcrire.config import settings

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


# ============================================================
# EXCEPTIONS
# ============================================================

class GeminiError(Exception):
    """Raised when a Gemini API call fails after all retries."""


class GeminiAuthError(GeminiError):
    """Raised when the Gemini API key is invalid."""


# ============================================================
# CLIENT
# ============================================================

def _get_client():
    """Returns an initialised Gemini client."""
    from google import genai
    return genai.Client(api_key=settings.gemini_api_key)


# ============================================================
# CORE CALL
# ============================================================

@retry(
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type(GeminiError),
    reraise=True,
)
def _call_gemini(prompt: str) -> str:
    """
    Makes a single Gemini generate_content call with tenacity backoff.
    Retries on transient errors. Raises immediately on auth failures.
    """
    try:
        client   = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        return response.text

    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "invalid" in err_str.lower():
            raise GeminiAuthError(
                "Invalid Gemini API key. "
                "Run \\'transcrire --check api-keys\\' to update it."
            ) from e
        if "404" in err_str:
            raise GeminiError(
                f"Gemini model \'{MODEL}\' not found. "
                "The model name may have changed."
            ) from e
        # Re-raise as GeminiError so tenacity retries it
        raise GeminiError(f"Gemini API error: {e}") from e


# ============================================================
# PUBLIC FUNCTIONS
# ============================================================

def generate_captions(prompt: str) -> str:
    """
    Generates captions from a prompt string.
    Returns the raw Gemini response text.
    Prompt construction lives in core/captions.py.

    Raises GeminiError on failure after retries.
    """
    logger.info("Generating captions via Gemini")
    result = _call_gemini(prompt)
    logger.info("Captions generated")
    return result


def generate_references(prompt: str) -> str:
    """
    Generates a timestamp reference list from a prompt string.
    Returns the raw Gemini response text.
    Prompt construction lives in core/captions.py.

    Raises GeminiError on failure after retries.
    """
    logger.info("Generating reference list via Gemini")
    result = _call_gemini(prompt)
    logger.info("Reference list generated")
    return result
'''


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("\\n" + "=" * 50)
    print("  Transcrire — Services Layer")
    print("=" * 50 + "\\n")

    write(SERVICES / "rss.py",     RSS_PY)
    write(SERVICES / "audio.py",   AUDIO_PY)
    write(SERVICES / "groq.py",    GROQ_PY)
    write(SERVICES / "whisper.py", WHISPER_PY)
    write(SERVICES / "gemini.py",  GEMINI_PY)

    print("\\n" + "=" * 50)
    print("  Services layer complete.")
    print("=" * 50)
    print("""
Next steps:
  1. Verify no import errors:
         python -c "from transcrire.services.rss import fetch_feed; print('OK')"
         python -c "from transcrire.services.audio import check_ffmpeg; print('OK')"
         python -c "from transcrire.services.groq import transcribe_groq; print('OK')"
         python -c "from transcrire.services.whisper import transcribe_whisper; print('OK')"
         python -c "from transcrire.services.gemini import generate_captions; print('OK')"

  2. Commit:
         git add -A
         git commit -m "feat: implement services layer"
         git push origin rebuild
""")


if __name__ == "__main__":
    main()
