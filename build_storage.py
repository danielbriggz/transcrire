"""
Transcrire — Storage Layer Build Script
=========================================
Run from the project root:
    python build_storage.py

Writes:
  - transcrire/storage/episodes.py
  - transcrire/storage/assets.py

storage/db.py was written in the database layer step.
Overwrites existing placeholder files.
"""

from pathlib import Path

ROOT    = Path(__file__).parent
STORAGE = ROOT / "transcrire" / "storage"


# ============================================================
# HELPERS
# ============================================================

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  WRITTEN: {path}")


# ============================================================
# episodes.py
# ============================================================

EPISODES_PY = '''\
# ============================================================
# Transcrire — Episode Storage
# ============================================================
# All filesystem operations for episodes:
#   - Creating per-episode output folder structure
#   - Saving transcripts, captions, and images to disk
#   - Writing the manifest sidecar after each stage
#   - Downloading audio and cover art from URLs
#
# No business logic lives here — this layer only persists
# what core/ has already prepared.
#
# Usage:
#   from transcrire.storage.episodes import create_episode_folder
# ============================================================

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from transcrire.config import settings
from transcrire.domain.episode import Episode
from transcrire.domain.stage_result import StageResult

logger = logging.getLogger(__name__)


# ============================================================
# EPISODE PATHS
# ============================================================

@dataclass
class EpisodePaths:
    """
    Typed paths for all subdirectories within an episode folder.
    Attribute access only — no string key lookups.

    Attributes:
        root:        Top-level episode folder.
        transcripts: Where transcript files are saved.
        captions:    Where caption files are saved.
        images:      Where cover art and quote cards are saved.
    """
    root:        Path
    transcripts: Path
    captions:    Path
    images:      Path


def create_episode_folder(safe_title: str, season: int, episode: int) -> EpisodePaths:
    """
    Creates the per-episode output folder structure.
    Folder name format: {safe_title} - S{season}E{episode}

    Args:
        safe_title: Filesystem-safe episode title.
        season:     Season number.
        episode:    Episode number.

    Returns:
        EpisodePaths with all subdirectory paths.
    """
    folder_name = f"{safe_title} - S{season}E{episode}"
    root        = settings.output_folder / folder_name

    paths = EpisodePaths(
        root        = root,
        transcripts = root / "transcripts",
        captions    = root / "captions",
        images      = root / "images",
    )

    for path in (paths.root, paths.transcripts, paths.captions, paths.images):
        path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Episode folder created",
        extra={"folder": str(root)},
    )
    return paths


# ============================================================
# FILE SAVING
# ============================================================

def save_transcript(
    transcript: str,
    episode: Episode,
    paths: EpisodePaths,
    suffix: str = "",
) -> Path:
    """
    Saves a transcript string to the episode\'s transcripts folder.

    Args:
        transcript: Transcript text to save.
        episode:    Episode domain object (for filename).
        paths:      EpisodePaths for this episode.
        suffix:     Filename suffix e.g. "_segments", "_words". Default "".

    Returns:
        Path to the saved transcript file.
    """
    filename = f"{episode.safe_title} - {episode.identifier}{suffix}.txt"
    output   = paths.transcripts / filename
    output.write_text(transcript, encoding="utf-8")

    logger.info("Transcript saved", extra={"path": str(output)})
    return output


def save_pc_transcript(
    transcript: str,
    source_filename: str,
    suffix: str = "",
) -> Path:
    """
    Saves a transcript from a PC upload to the pc_transcripts folder.
    Strips any _temp_ prefix from the source filename.

    Args:
        transcript:       Transcript text to save.
        source_filename:  Original audio filename.
        suffix:           Transcript type suffix.

    Returns:
        Path to the saved transcript file.
    """
    pc_folder = settings.output_folder / "pc_transcripts"
    pc_folder.mkdir(parents=True, exist_ok=True)

    # Strip _temp_ prefix added during file handling
    clean_name = source_filename.replace("_temp_", "")
    stem       = Path(clean_name).stem
    output     = pc_folder / f"{stem}{suffix}.txt"
    output.write_text(transcript, encoding="utf-8")

    logger.info("PC transcript saved", extra={"path": str(output)})
    return output


def save_captions(
    captions_text: str,
    episode: Episode,
    paths: EpisodePaths,
    platform: str,
    pending_review: bool = False,
) -> Path:
    """
    Saves caption text to the episode\'s captions folder.

    Args:
        captions_text:  Caption text to save.
        episode:        Episode domain object.
        paths:          EpisodePaths for this episode.
        platform:       Platform name e.g. "twitter".
        pending_review: If True, marks file as pipeline-generated
                        (not manually reviewed). Stored in DB —
                        filename stays clean.

    Returns:
        Path to the saved captions file.
    """
    filename = f"{episode.safe_title}_{platform}_captions.txt"
    output   = paths.captions / filename
    output.write_text(captions_text, encoding="utf-8")

    logger.info(
        "Captions saved",
        extra={"path": str(output), "pending_review": pending_review},
    )
    return output


def save_references(
    references_text: str,
    episode: Episode,
    paths: EpisodePaths,
    platform: str,
) -> Path:
    """
    Saves a timestamp reference list to the captions folder.

    Args:
        references_text: Reference list text from Gemini.
        episode:         Episode domain object.
        paths:           EpisodePaths for this episode.
        platform:        Platform name e.g. "twitter".

    Returns:
        Path to the saved references file.
    """
    filename = f"{episode.safe_title}_{platform}_references.txt"
    output   = paths.captions / filename

    header = f"CAPTION REFERENCES — {platform.upper()}\n{'=' * 40}\n\n"
    output.write_text(header + references_text, encoding="utf-8")

    logger.info("References saved", extra={"path": str(output)})
    return output


def save_image(image, output_path: Path) -> Path:
    """
    Saves a PIL Image object to disk as a JPEG.

    Args:
        image:       PIL Image object from core/images.py.
        output_path: Full path to write the image to.

    Returns:
        output_path on success.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(output_path), quality=95)
    logger.info("Image saved", extra={"path": str(output_path)})
    return output_path


# ============================================================
# ASSET DOWNLOADS
# ============================================================

def download_audio(audio_url: str, episode: Episode) -> Path:
    """
    Downloads episode audio from a URL to the input folder.

    Args:
        audio_url: Direct URL to the audio file.
        episode:   Episode domain object (for filename).

    Returns:
        Path to the downloaded audio file.

    Raises:
        httpx.HTTPError on network failure.
    """
    filename   = f"{episode.safe_title} - {episode.identifier}.mp3"
    output     = settings.input_folder / filename
    settings.input_folder.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading audio", extra={"url": audio_url})

    with httpx.stream("GET", audio_url, follow_redirects=True) as response:
        response.raise_for_status()
        with open(output, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)

    logger.info("Audio downloaded", extra={"path": str(output)})
    return output


def download_cover_art(cover_url: str, episode: Episode, paths: EpisodePaths) -> Path:
    """
    Downloads episode cover art from a URL to the images folder.

    Args:
        cover_url: Direct URL to the cover art image.
        episode:   Episode domain object (for filename).
        paths:     EpisodePaths for this episode.

    Returns:
        Path to the downloaded cover art file.

    Raises:
        httpx.HTTPError on network failure.
    """
    filename = f"{episode.safe_title} - {episode.identifier}_cover.jpg"
    output   = paths.images / filename

    logger.info("Downloading cover art", extra={"url": cover_url})

    response = httpx.get(cover_url, follow_redirects=True)
    response.raise_for_status()
    output.write_bytes(response.content)

    logger.info("Cover art downloaded", extra={"path": str(output)})
    return output


# ============================================================
# MANIFEST SIDECAR
# ============================================================

def write_manifest(episode: Episode, stage_results: list[StageResult]) -> Path:
    """
    Writes or updates the manifest.json sidecar in the episode folder.
    Called after every successful stage completion.

    The manifest is a read-only export — the database is always
    authoritative. It exists to support \'transcrire recover\' when
    the database is lost or the folder is moved to a new machine.

    Args:
        episode:       Episode domain object with folder_path set.
        stage_results: All stage results for this episode.

    Returns:
        Path to the written manifest file.
    """
    if not episode.folder_path:
        logger.warning(
            "Cannot write manifest — episode has no folder_path",
            extra={"episode": episode.identifier},
        )
        return None

    stages_data = {}
    for result in stage_results:
        stages_data[result.stage.value] = {
            "status":       result.status.value,
            "output_paths": [str(p) for p in result.output_paths],
            "completed_at": result.created_at.isoformat(),
        }

    manifest = {
        "podcast_name": episode.podcast_name,
        "season":       episode.season,
        "episode":      episode.episode,
        "title":        episode.title,
        "safe_title":   episode.safe_title,
        "spotify_link": episode.spotify_link,
        "stages":       stages_data,
        "written_at":   datetime.utcnow().isoformat(),
    }

    manifest_path = episode.folder_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Manifest written", extra={"path": str(manifest_path)})
    return manifest_path


def read_manifest(folder_path: Path) -> dict | None:
    """
    Reads a manifest.json from an episode folder.
    Used by \'transcrire recover\' to reconstruct DB rows.

    Args:
        folder_path: Path to the episode output folder.

    Returns:
        Manifest dict, or None if not found or unreadable.
    """
    manifest_path = folder_path / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(
            "Could not read manifest",
            extra={"path": str(manifest_path), "error": str(e)},
        )
        return None
'''


# ============================================================
# assets.py
# ============================================================

ASSETS_PY = '''\
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
    Finds the cover art file in an episode\'s images folder.
    Returns the most recently modified cover file if multiple exist.

    Args:
        images_folder: Path to the episode\'s images subdirectory.

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
            f"Unsupported audio format: {path.suffix}\\n"
            "Supported formats: .mp3, .wav, .m4a"
        )
'''


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("\n" + "=" * 50)
    print("  Transcrire — Storage Layer")
    print("=" * 50 + "\n")

    write(STORAGE / "episodes.py", EPISODES_PY)
    write(STORAGE / "assets.py",   ASSETS_PY)

    print("\n" + "=" * 50)
    print("  Storage layer complete.")
    print("=" * 50)
    print("""
Next steps:
  1. Verify no import errors:
         python -c "from transcrire.storage.episodes import create_episode_folder; print('OK')"
         python -c "from transcrire.storage.assets import ensure_fonts; print('OK')"

  2. Commit:
         git add -A
         git commit -m "feat: implement storage layer"
         git push origin rebuild
""")


if __name__ == "__main__":
    main()
