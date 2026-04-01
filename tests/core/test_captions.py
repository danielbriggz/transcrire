# ============================================================
# Tests -- core/captions.py
# ============================================================
# Tests for prompt building, caption parsing, replacement,
# formatting, and URL stripping.
# All pure functions -- no I/O, no API calls.
# ============================================================

import pytest

from transcrire.core.captions import (
    PLATFORMS,
    build_caption_prompt,
    build_reference_prompt,
    build_single_caption_prompt,
    parse_captions,
    replace_caption,
    format_captions,
    strip_urls,
)


class TestPlatforms:

    def test_all_expected_platforms_present(self):
        assert "twitter"  in PLATFORMS
        assert "linkedin" in PLATFORMS
        assert "facebook" in PLATFORMS

    def test_platform_has_name_and_instruction(self):
        for name, platform in PLATFORMS.items():
            assert platform.name == name
            assert platform.instruction
            assert "{link}" in platform.instruction


class TestBuildCaptionPrompt:

    def test_prompt_contains_transcript(self):
        platform = PLATFORMS["twitter"]
        prompt   = build_caption_prompt(platform, "My transcript text", "https://spotify.com/ep1")
        assert "My transcript text" in prompt

    def test_prompt_contains_link(self):
        platform = PLATFORMS["twitter"]
        prompt   = build_caption_prompt(platform, "transcript", "https://spotify.com/ep1")
        assert "https://spotify.com/ep1" in prompt

    def test_prompt_contains_platform_instruction(self):
        platform = PLATFORMS["twitter"]
        prompt   = build_caption_prompt(platform, "transcript", "https://link.com")
        assert "tweet" in prompt.lower()

    def test_prompt_with_empty_link(self):
        platform = PLATFORMS["facebook"]
        prompt   = build_caption_prompt(platform, "transcript", "")
        assert "transcript" in prompt

    def test_all_platforms_build_prompts(self):
        for platform in PLATFORMS.values():
            prompt = build_caption_prompt(platform, "transcript", "https://link.com")
            assert len(prompt) > 50


class TestBuildReferencePrompt:

    def test_contains_transcript(self):
        prompt = build_reference_prompt("twitter", "my transcript", "my captions")
        assert "my transcript" in prompt

    def test_contains_captions(self):
        prompt = build_reference_prompt("twitter", "transcript", "my captions")
        assert "my captions" in prompt

    def test_contains_platform_name(self):
        prompt = build_reference_prompt("linkedin", "transcript", "captions")
        assert "linkedin" in prompt.lower()

    def test_reference_format_instructions_present(self):
        prompt = build_reference_prompt("twitter", "transcript", "captions")
        assert "Caption 1" in prompt
        assert "HH:MM:SS" in prompt


class TestParseCaptions:

    def test_parses_numbered_captions(self):
        raw    = "1. First caption text\n\n2. Second caption text\n\n3. Third caption text"
        result = parse_captions(raw)
        assert len(result) == 3
        assert result[0] == "First caption text"
        assert result[1] == "Second caption text"

    def test_strips_leading_numbers(self):
        raw    = "1. Caption without number"
        result = parse_captions(raw)
        assert result[0] == "Caption without number"
        assert not result[0].startswith("1.")

    def test_handles_single_caption(self):
        raw    = "1. Only one caption"
        result = parse_captions(raw)
        assert len(result) == 1

    def test_skips_empty_entries(self):
        raw    = """1. First\n\n
        2. Second"""
        result = parse_captions(raw)
        assert all(c for c in result)

    def test_handles_multiline_caption(self):
        raw    = "1. First line\n\nSecond line of same caption\n\n2. Another caption"
        result = parse_captions(raw)
        assert len(result) == 2
        assert "First line" in result[0]


class TestReplaceCaption:

    def test_replaces_at_index(self):
        captions = ["First", "Second", "Third"]
        result   = replace_caption(captions, 1, "New Second")
        assert result[1] == "New Second"

    def test_does_not_mutate_original(self):
        captions = ["First", "Second", "Third"]
        result   = replace_caption(captions, 0, "New First")
        assert captions[0] == "First"
        assert result[0]   == "New First"

    def test_strips_whitespace_from_replacement(self):
        captions = ["First", "Second"]
        result   = replace_caption(captions, 0, "  Trimmed  ")
        assert result[0] == "Trimmed"

    def test_other_captions_unchanged(self):
        captions = ["First", "Second", "Third"]
        result   = replace_caption(captions, 1, "New")
        assert result[0] == "First"
        assert result[2] == "Third"


class TestFormatCaptions:

    def test_numbers_captions_from_one(self):
        captions = ["First", "Second", "Third"]
        result   = format_captions(captions)
        assert result.startswith("1. First")
        assert "2. Second" in result
        assert "3. Third" in result

    def test_single_caption(self):
        result = format_captions(["Only one"])
        assert result == "1. Only one"

    def test_empty_list(self):
        result = format_captions([])
        assert result == ""

    def test_captions_separated_by_blank_line(self):
        captions = ["First", "Second"]
        result   = format_captions(captions)
        assert "" in result

    def test_roundtrip_parse_format(self):
        original  = ["First caption", "Second caption", "Third caption"]
        formatted = format_captions(original)
        parsed    = parse_captions(formatted)
        assert parsed == original


class TestStripUrls:

    def test_removes_http_url(self):
        text   = "Great episode http://example.com listen now"
        result = strip_urls(text)
        assert "http://example.com" not in result
        assert "Great episode" in result

    def test_removes_https_url(self):
        text   = "Check this out https://spotify.com/episode/abc123"
        result = strip_urls(text)
        assert "https://" not in result

    def test_no_url_unchanged(self):
        text = "No URLs in this caption text"
        assert strip_urls(text) == text

    def test_removes_multiple_urls(self):
        text   = "Link one https://a.com and link two https://b.com here"
        result = strip_urls(text)
        assert "https://" not in result

    def test_strips_trailing_whitespace(self):
        text   = "Caption text https://link.com"
        result = strip_urls(text)
        assert not result.endswith(" ")


class TestBuildSingleCaptionPrompt:

    def test_contains_platform_name(self):
        platform = PLATFORMS["twitter"]
        prompt   = build_single_caption_prompt(
            platform, "1. Cap one\n2. Cap two", "Cap one", "https://link.com""",
        )
        assert "twitter" in prompt.lower()

    def test_contains_caption_to_replace(self):
        platform = PLATFORMS["twitter"]
        prompt   = build_single_caption_prompt(
            platform, "all captions", "specific caption to replace", "https://link.com",
        )
        assert "specific caption to replace" in prompt

    def test_contains_spotify_link(self):
        platform = PLATFORMS["facebook"]
        prompt   = build_single_caption_prompt(
            platform, "all captions", "old caption", "https://spotify.com/ep42",
        )
        assert "https://spotify.com/ep42" in prompt
