# ============================================================
# Tests -- core/images.py
# ============================================================
# Tests for background brightness detection, word wrap,
# and overlay constants. Uses tmp_path for image fixtures.
# Image building (build_quote_card) requires font files
# on disk -- marked integration and skipped by default.
# ============================================================

import pytest
from pathlib import Path

from transcrire.core.images import (
    detect_font_weight,
    wrap_text,
    OVERLAY_DEFAULT,
    OVERLAY_LIGHT,
    OVERLAY_DARK,
    BRIGHTNESS_DARK_THRESHOLD,
    CARD_SIZE,
    FONT_SIZE,
    MARGIN,
)
from transcrire.domain.enums import FontWeight


class TestConstants:

    def test_card_size_is_square(self):
        assert CARD_SIZE[0] == CARD_SIZE[1]

    def test_overlay_ordering(self):
        assert OVERLAY_LIGHT < OVERLAY_DEFAULT < OVERLAY_DARK

    def test_overlay_values_in_valid_range(self):
        for value in (OVERLAY_LIGHT, OVERLAY_DEFAULT, OVERLAY_DARK):
            assert 0 <= value <= 255

    def test_font_size_is_positive(self):
        assert FONT_SIZE > 0

    def test_margin_is_positive(self):
        assert MARGIN > 0

    def test_margin_smaller_than_card_width(self):
        assert MARGIN < CARD_SIZE[0]


class TestDetectFontWeight:

    def test_dark_image_returns_semibold(self, tmp_path):
        from PIL import Image
        img  = Image.new("RGB", (100, 100), color=(10, 10, 10))
        path = tmp_path / "dark_cover.jpg"
        img.save(str(path))
        assert detect_font_weight(path) == FontWeight.SEMIBOLD

    def test_light_image_returns_medium(self, tmp_path):
        from PIL import Image
        img  = Image.new("RGB", (100, 100), color=(240, 240, 240))
        path = tmp_path / "light_cover.jpg"
        img.save(str(path))
        assert detect_font_weight(path) == FontWeight.MEDIUM

    def test_threshold_boundary_dark_side(self, tmp_path):
        from PIL import Image
        brightness = BRIGHTNESS_DARK_THRESHOLD - 1
        img  = Image.new("L", (100, 100), color=brightness)
        path = tmp_path / "threshold_dark.jpg"
        img.save(str(path))
        assert detect_font_weight(path) == FontWeight.SEMIBOLD

    def test_threshold_boundary_light_side(self, tmp_path):
        from PIL import Image
        brightness = BRIGHTNESS_DARK_THRESHOLD
        img  = Image.new("L", (100, 100), color=brightness)
        path = tmp_path / "threshold_light.jpg"
        img.save(str(path))
        assert detect_font_weight(path) == FontWeight.MEDIUM

    def test_missing_file_returns_medium_default(self, tmp_path):
        result = detect_font_weight(tmp_path / "nonexistent.jpg")
        assert result == FontWeight.MEDIUM


class TestWrapText:

    def _make_font(self):
        from PIL import ImageFont
        return ImageFont.load_default()

    def test_short_text_fits_one_line(self):
        font   = self._make_font()
        result = wrap_text("Hi", font, max_width=500)
        assert len(result) == 1
        assert result[0] == "Hi"

    def test_empty_string_returns_empty_list(self):
        font   = self._make_font()
        result = wrap_text("", font, max_width=500)
        assert result == []

    def test_long_text_wraps_to_multiple_lines(self):
        font      = self._make_font()
        long_text = " ".join(["word"] * 30)
        result    = wrap_text(long_text, font, max_width=50)
        assert len(result) > 1

    def test_all_words_preserved(self):
        font     = self._make_font()
        text     = "The quick brown fox jumps over the lazy dog"
        result   = wrap_text(text, font, max_width=100)
        rejoined = " ".join(result)
        for word in text.split():
            assert word in rejoined

    def test_single_word_never_split(self):
        font   = self._make_font()
        result = wrap_text("Superlongword", font, max_width=10)
        assert len(result) >= 1
        assert "Superlongword" in " ".join(result)

    def test_wide_max_width_single_line(self):
        font   = self._make_font()
        result = wrap_text("Short text", font, max_width=10000)
        assert len(result) == 1

    def test_no_empty_lines_in_output(self):
        font   = self._make_font()
        result = wrap_text("Some words here", font, max_width=200)
        for line in result:
            assert line.strip() != ""
