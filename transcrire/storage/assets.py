# ============================================================
# Transcrire — Asset Storage
# ============================================================
# Manages fonts, cover art resolution, and audio file
# discovery. Lazy validation — checked at first use,
# not on every launch.
#
# Usage:
#   from transcrire.storage.assets import ensure_fonts
# ============================================================

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from transcrire.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# FONT URLS
# Direct .ttf URLs from Google Fonts CDN.
# ============================================================

FONT_URLS: dict[str, str] = {
    "AtkinsonHyperlegibleMono-ExtraLight": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZnNeiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-Light": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZQteiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-Regular": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZHNeiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-Medium": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZLteiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-SemiBold": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZwtCiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-Bold": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZ-9CiDQ.ttf"
    ),
    "AtkinsonHyperlegibleMono-ExtraBold": (
        "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/"
        "tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZnNCiDQ.ttf"
    ),
}

# Proxy for "all fonts present" — if Medium exists, all do
_SENTINEL_FONT = "AtkinsonHyperlegibleMono-Medium"


# ============================================================
# FONT MANAGEMENT
# ============================================================

def fonts_present() -> bool:
    """
    Checks whether the required fonts are available.
    Uses Medium weight as a proxy for all weights.
    """
    sentinel = settings.fonts_dir / f"{_SENTINEL_FONT}.ttf"
    return sentinel.exists()


def ensure_fonts() -> None:
    """
    Downloads all Atkinson Hyperlegible Mono font weights
    if they are not already present.
    Called lazily at first image generation — not on launch.

    Raises:
        httpx.HTTPError if a font download fails.
    """
    if fonts_present():
        logger.debug("Fonts already present")
        return

    logger.info("Fonts not found — downloading from Google Fonts")
    settings.fonts_dir.mkdir(parents=True, exist_ok=True)

    for name, url in FONT_URLS.items():
        dest = settings.fonts_dir / f"{name}.ttf"
        logger.info("Downloading font", extra={"font": name})
        response = httpx.get(url)
        response.raise_for_status()
        dest.write_bytes(response.content)
        logger.info("Font downloaded", extra={"font": name})

    logger.info("All fonts downloaded")


# ============================================================
# COVER ART RESOLUTION
# ============================================================

def find_cover_art(images_folder: Path) -> Path | None:
    """
    Finds the cover art file in an episode's images folder.
    Returns the most recently modified cover file if multiple exist.

    Args:
        images_folder: Path to the episode's images subdirectory.

    Returns:
        Path to the cover art file, or None if not found.
    """
    if not images_folder.exists():
        return None

    covers = sorted(
        [
            f for f in images_folder.iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg", ".png")
            and f.stem.endswith("_cover")
        ],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not covers:
        return None

    return covers[0]


# ============================================================
# AUDIO FILE MANAGEMENT
# ============================================================

def find_audio_files() -> list[Path]:
    """
    Returns all supported audio files in the input folder,
    sorted by modification time (most recent first).
    """
    if not settings.input_folder.exists():
        return []

    return sorted(
        [
            f for f in settings.input_folder.iterdir()
            if f.suffix.lower() in (".mp3", ".wav", ".m4a")
        ],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )


def most_recent_audio() -> Path | None:
    """
    Returns the most recently modified audio file in the
    input folder, or None if no audio files are found.
    """
    files = find_audio_files()
    return files[0] if files else None


def validate_audio_path(path: Path) -> None:
    """
    Validates that a given audio path exists and is a supported format.

    Args:
        path: Path to validate.

    Raises:
        FileNotFoundError if the file does not exist.
        ValueError if the file format is not supported.
    """
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if path.suffix.lower() not in (".mp3", ".wav", ".m4a"):
        raise ValueError(
            f"Unsupported audio format: {path.suffix}\n"
            "Supported formats: .mp3, .wav, .m4a"
        )
