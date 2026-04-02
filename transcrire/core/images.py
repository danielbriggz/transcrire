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

CARD_SIZE          = (1080, 1350)
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
        pixel_data    =img.tobytes()
        avg_brightness = sum(pixel_data) / (img.width * img.height)

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
            f"Font file not found: {font_path}\n"
            "Run \'transcrire --check fonts\' to download fonts."
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
    podcast_name: str = "",
    episode_title: str = "",
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

    # ---- Metadata line ----
        # Podcast name and episode title rendered at the bottom
        # in a smaller font size than the quote text.
        if podcast_name or episode_title:
            meta_parts = [p for p in [podcast_name, episode_title] if p]
            meta_text  = "  |  ".join(meta_parts)
            meta_size  = FONT_SIZE - 12  # 22px vs 34px for quote
            try:
                meta_font = ImageFont.truetype(
                    str(fonts_dir / f"AtkinsonHyperlegibleMono-{font_weight.value}.ttf"),
                    meta_size,
                )
                meta_bbox = draw.textbbox((0, 0), meta_text, font=meta_font)
                meta_w    = meta_bbox[2] - meta_bbox[0]
                meta_x    = (W - meta_w) // 2
                meta_y    = H - MARGIN - (meta_size + 8)
                draw.text((meta_x + 1, meta_y + 1), meta_text, font=meta_font, fill=(0, 0, 0, 180))
                draw.text((meta_x, meta_y), meta_text, font=meta_font, fill=(255, 255, 255, 200))
            except Exception:
                pass  # Never let metadata rendering break the card

    return bg.convert("RGB")
