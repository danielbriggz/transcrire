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
            "ffmpeg not found on PATH.\n"
            "Install it from https://ffmpeg.org/download.html\n"
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
                f"ffmpeg compression failed:\n{result.stderr.decode().strip()}"
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
                f"ffmpeg split failed:\n{result.stderr.decode().strip()}"
            )
    except FileNotFoundError as e:
        raise FFmpegNotFoundError("ffmpeg not found on PATH.") from e

    chunks = sorted(chunks_dir.glob(f"{base}_chunk_*.mp3"))

    if not chunks:
        raise AudioError("ffmpeg produced no chunk files. Check the audio file.")

    logger.info("Audio split complete", extra={"chunks": len(chunks)})
    return chunks
