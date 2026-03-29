"""
Transcrire — Core Layer Build Script
======================================
Run from the project root:
    python build_core.py

Writes:
  - transcrire/core/transcript.py
  - transcrire/core/captions.py
  - transcrire/core/images.py
  - transcrire/core/pipeline.py

All pure business logic — no I/O, no API calls, fully testable.
Overwrites existing placeholder files.
"""

from pathlib import Path

ROOT = Path(__file__).parent
CORE = ROOT / "transcrire" / "core"


# ============================================================
# HELPERS
# ============================================================

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  WRITTEN: {path}")


# ============================================================
# transcript.py
# ============================================================

TRANSCRIPT_PY = '''\
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
        return "\\n".join(lines)

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
'''


# ============================================================
# captions.py
# ============================================================

CAPTIONS_PY = '''\
# ============================================================
# Transcrire — Captions Core Logic
# ============================================================
# Pure functions for caption prompt building, parsing,
# and reference list prompt building.
# No I/O — takes/returns strings and lists.
#
# Usage:
#   from transcrire.core.captions import build_caption_prompt
# ============================================================

from __future__ import annotations

import re
from dataclasses import dataclass


# ============================================================
# PLATFORM DEFINITIONS
# ============================================================

@dataclass(frozen=True)
class Platform:
    """
    Defines a social media platform\'s caption requirements.
    Instruction uses {link} placeholder filled at prompt build time.
    """
    name:        str
    instruction: str


PLATFORMS: dict[str, Platform] = {
    "twitter": Platform(
        name="twitter",
        instruction=(
            "Format each one as a short tweet (under 250 characters) "
            "followed by this link: {link}\\n"
            "Number them 1 to 5.\\n"
            "Only return the 5 tweets, nothing else."
        ),
    ),
    "linkedin": Platform(
        name="linkedin",
        instruction=(
            "Format each one as a professional post (3-4 sentences with context). "
            "End each with a reflective question and this link: {link}\\n"
            "Number them 1 to 5.\\n"
            "Only return the 5 posts, nothing else."
        ),
    ),
    "facebook": Platform(
        name="facebook",
        instruction=(
            "Format each one as a warm, conversational post that encourages "
            "listeners to share their thoughts. End each with this link: {link}\\n"
            "Number them 1 to 5.\\n"
            "Only return the 5 posts, nothing else."
        ),
    ),
}


# ============================================================
# PROMPT BUILDERS
# ============================================================

def build_caption_prompt(
    platform: Platform,
    transcript: str,
    spotify_link: str,
) -> str:
    """
    Builds the Gemini prompt for caption generation.

    Args:
        platform:     Platform definition with instruction template.
        transcript:   Episode transcript text.
        spotify_link: Episode link to embed in captions.

    Returns:
        Complete prompt string ready for Gemini.
    """
    instruction = platform.instruction.format(link=spotify_link or "")

    return f"""You are a social media assistant for a podcast.
Read this transcript and pick 5 of the most interesting, thought-provoking, \
or quotable moments. Draw from across the episode. Prioritise moments that \
challenge assumptions or reframe familiar ideas.
The tone is casual and conversational with a gentle, philosophical approach.
Do not hallucinate. Do not make up anything outside the transcript.
{instruction}

Transcript:
{transcript}
"""


def build_reference_prompt(
    platform_name: str,
    transcript: str,
    captions_text: str,
) -> str:
    """
    Builds the Gemini prompt for reference list generation.
    Only used when a timestamped transcript was used for captions.

    Args:
        platform_name: Name of the platform (for labelling).
        transcript:    The timestamped transcript used.
        captions_text: The approved captions text to map back.

    Returns:
        Complete prompt string ready for Gemini.
    """
    return f"""You are a research assistant for a podcast editor.
Below is a timestamped transcript and a set of {platform_name} captions \
generated from it.
For each caption, identify the exact transcript segment it was drawn from.

Return a plain text reference list in this format:
Caption 1: [HH:MM:SS - HH:MM:SS] "exact or near-exact quote from transcript"
Caption 2: [HH:MM:SS - HH:MM:SS] "exact or near-exact quote from transcript"
...and so on.

Only return the reference list, nothing else.

Transcript:
{transcript}

Captions:
{captions_text}
"""


# ============================================================
# CAPTION PARSING
# ============================================================

def parse_captions(raw: str) -> list[str]:
    """
    Parses a raw Gemini caption response into a list of
    individual caption strings.

    Splits on numbered lines (1. 2. 3. etc.) and strips
    leading numbers from each entry.

    Args:
        raw: Raw text response from Gemini.

    Returns:
        List of individual caption strings, numbers stripped.
    """
    # Split on lines starting with a number and period
    parts = re.split(r"\\n(?=\\d+\\.\\s)", raw.strip())
    captions = []
    for part in parts:
        # Strip leading number and whitespace
        clean = re.sub(r"^\\d+\\.\\s*", "", part.strip())
        if clean:
            captions.append(clean)
    return captions


def replace_caption(
    captions: list[str],
    index: int,
    replacement: str,
) -> list[str]:
    """
    Replaces a single caption at the given index.
    Returns a new list — does not mutate the original.

    Args:
        captions:    Current list of caption strings.
        index:       Zero-based index of the caption to replace.
        replacement: New caption text (without leading number).

    Returns:
        New list with the replacement applied.
    """
    updated = list(captions)
    updated[index] = replacement.strip()
    return updated


def format_captions(captions: list[str]) -> str:
    """
    Formats a list of captions back into a numbered string
    for display or saving to disk.

    Args:
        captions: List of caption strings without numbers.

    Returns:
        Numbered string, one caption per block separated by
        a blank line.
    """
    return "\\n\\n".join(
        f"{i + 1}. {caption}" for i, caption in enumerate(captions)
    )


def strip_urls(text: str) -> str:
    """
    Removes all URLs from a caption string.
    Used before rendering text onto quote card images.
    """
    return re.sub(r"http\\S+", "", text).strip()


def build_single_caption_prompt(
    platform: Platform,
    all_captions_text: str,
    caption_to_replace: str,
    spotify_link: str,
) -> str:
    """
    Builds a targeted prompt to regenerate a single caption
    in the same style as the rest of the set.

    Args:
        platform:           Platform definition.
        all_captions_text:  Full current captions for context.
        caption_to_replace: The specific caption being replaced.
        spotify_link:       Episode link for the replacement.

    Returns:
        Prompt string for Gemini.
    """
    return f"""You are a social media assistant for a podcast.
Below is a set of {platform.name} captions. One of them needs to be replaced.

Here are all the current captions for context:
{all_captions_text}

The caption to replace is:
{caption_to_replace}

Write ONE new {platform.name} caption in exactly the same style, tone and \
format as the others. It must cover a different moment from the transcript \
than the one it is replacing. End it with the same episode link used in \
the others: {spotify_link}

Return only the new caption text, nothing else. Do not number it.
"""
'''


# ============================================================
# images.py
# ============================================================

IMAGES_PY = '''\
# ============================================================
# Transcrire — Image Composition Core Logic
# ============================================================
# Pure functions for quote card image generation.
# Pillow operations are here — but no file I/O.
# Saving lives in storage/episodes.py.
#
# Usage:
#   from transcrire.core.images import build_quote_card
# ============================================================

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from transcrire.domain.enums import FontWeight

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

CARD_SIZE          = (1080, 1080)
FONT_SIZE          = 34
LINE_SPACING       = 16
MARGIN             = 100
BLUR_RADIUS        = 6
JPEG_QUALITY       = 95

# Overlay opacity values — named constants, not magic numbers
OVERLAY_DEFAULT    = 160   # ~63% opacity — default
OVERLAY_LIGHT      = 120   # ~47% opacity — lighter variant
OVERLAY_DARK       = 200   # ~78% opacity — darker variant

# Brightness threshold for font weight selection
BRIGHTNESS_DARK_THRESHOLD = 100


# ============================================================
# BACKGROUND BRIGHTNESS
# ============================================================

def detect_font_weight(cover_path: Path) -> FontWeight:
    """
    Analyses cover art brightness to select an appropriate font weight.
    Dark backgrounds get SemiBold for readability.
    Light backgrounds get Medium since the overlay handles contrast.

    Args:
        cover_path: Path to the cover art image file.

    Returns:
        FontWeight enum value.
    """
    try:
        img = Image.open(cover_path).convert("L")
        pixel_data    = list(img.getdata())
        avg_brightness = sum(pixel_data) / len(pixel_data)

        if avg_brightness < BRIGHTNESS_DARK_THRESHOLD:
            logger.debug("Dark background detected", extra={"brightness": avg_brightness})
            return FontWeight.SEMIBOLD
        else:
            logger.debug("Light background detected", extra={"brightness": avg_brightness})
            return FontWeight.MEDIUM

    except Exception as e:
        logger.warning(
            "Brightness detection failed — defaulting to Medium",
            extra={"error": str(e)},
        )
        return FontWeight.MEDIUM


# ============================================================
# FONT LOADING
# ============================================================

def load_font(fonts_dir: Path, weight: FontWeight) -> ImageFont.FreeTypeFont:
    """
    Loads the Atkinson Hyperlegible Mono font at the configured weight.

    Args:
        fonts_dir: Path to the fonts directory.
        weight:    FontWeight enum value.

    Returns:
        PIL FreeTypeFont instance.

    Raises:
        FileNotFoundError if the font file is missing.
    """
    font_filename = f"AtkinsonHyperlegibleMono-{weight.value}.ttf"
    font_path     = fonts_dir / font_filename

    if not font_path.exists():
        raise FileNotFoundError(
            f"Font file not found: {font_path}\\n"
            "Run \\'transcrire --check fonts\\' to download fonts."
        )

    return ImageFont.truetype(str(font_path), FONT_SIZE)


# ============================================================
# WORD WRAP
# ============================================================

def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """
    Wraps text to fit within max_width pixels using the given font.
    Splits on word boundaries only.

    Args:
        text:      Text to wrap.
        font:      PIL font for measuring text width.
        max_width: Maximum line width in pixels.

    Returns:
        List of wrapped lines.
    """
    draw    = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words   = text.split()
    lines   : list[str] = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# QUOTE CARD BUILDER
# ============================================================

def build_quote_card(
    cover_path: Path,
    quote_text: str,
    fonts_dir: Path,
    overlay_opacity: int = OVERLAY_DEFAULT,
    size: tuple[int, int] = CARD_SIZE,
) -> Image.Image:
    """
    Builds a single quote card image in memory.
    Does not save to disk — caller handles saving.

    Process:
      1. Open and resize cover art
      2. Apply Gaussian blur to soften background
      3. Paste semi-transparent dark overlay
      4. Select font weight based on background brightness
      5. Word-wrap quote text to fit within margins
      6. Calculate vertical centre for text block
      7. Render drop shadow then white text per line

    Args:
        cover_path:      Path to the episode cover art.
        quote_text:      Caption text to render (URLs already stripped).
        fonts_dir:       Path to fonts directory.
        overlay_opacity: Darkness of the background overlay (0-255).
        size:            Image dimensions. Default 1080x1080.

    Returns:
        PIL Image object ready to save.

    Raises:
        FileNotFoundError if cover art or font files are missing.
    """
    W, H = size

    # ---- Background ----
    bg = Image.open(cover_path).convert("RGB")
    bg = bg.resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))

    # ---- Dark overlay ----
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, overlay_opacity))
    bg      = bg.convert("RGBA")
    bg.paste(overlay, (0, 0), overlay)

    # ---- Font ----
    font_weight = detect_font_weight(cover_path)
    font        = load_font(fonts_dir, font_weight)

    # ---- Word wrap ----
    max_width = W - (MARGIN * 2)
    lines     = wrap_text(quote_text, font, max_width)

    # ---- Vertical centring ----
    line_height  = FONT_SIZE + LINE_SPACING
    total_height = len(lines) * line_height
    y            = (H - total_height) // 2

    # ---- Text rendering ----
    draw = ImageDraw.Draw(bg)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x    = (W - (bbox[2] - bbox[0])) // 2
        # Drop shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
        # White text
        draw.text((x, y), line, font=font, fill="white")
        y += line_height

    return bg.convert("RGB")
'''


# ============================================================
# pipeline.py
# ============================================================

PIPELINE_PY = '''\
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
'''


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    print("\n" + "=" * 50)
    print("  Transcrire — Core Layer")
    print("=" * 50 + "\n")

    write(CORE / "transcript.py", TRANSCRIPT_PY)
    write(CORE / "captions.py",   CAPTIONS_PY)
    write(CORE / "images.py",     IMAGES_PY)
    write(CORE / "pipeline.py",   PIPELINE_PY)

    print("\n" + "=" * 50)
    print("  Core layer complete.")
    print("=" * 50)
    print("""
Next steps:
  1. Verify no import errors:
         python -c "from transcrire.core.transcript import stitch_transcripts; print('OK')"
         python -c "from transcrire.core.captions import build_caption_prompt; print('OK')"
         python -c "from transcrire.core.images import build_quote_card; print('OK')"
         python -c "from transcrire.core.pipeline import get_available_actions; print('OK')"

  2. Commit:
         git add -A
         git commit -m "feat: implement core layer"
         git push origin rebuild
""")


if __name__ == "__main__":
    main()
