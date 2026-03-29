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
    Defines a social media platform's caption requirements.
    Instruction uses {link} placeholder filled at prompt build time.
    """
    name:        str
    instruction: str


PLATFORMS: dict[str, Platform] = {
    "twitter": Platform(
        name="twitter",
        instruction=(
            "Format each one as a short tweet (under 250 characters) "
            "followed by this link: {link}\n"
            "Number them 1 to 5.\n"
            "Only return the 5 tweets, nothing else."
        ),
    ),
    "linkedin": Platform(
        name="linkedin",
        instruction=(
            "Format each one as a professional post (3-4 sentences with context). "
            "End each with a reflective question and this link: {link}\n"
            "Number them 1 to 5.\n"
            "Only return the 5 posts, nothing else."
        ),
    ),
    "facebook": Platform(
        name="facebook",
        instruction=(
            "Format each one as a warm, conversational post that encourages "
            "listeners to share their thoughts. End each with this link: {link}\n"
            "Number them 1 to 5.\n"
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
Read this transcript and pick 5 of the most interesting, thought-provoking, or quotable moments. Draw from across the episode. Prioritise moments that challenge assumptions or reframe familiar ideas.
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
Below is a timestamped transcript and a set of {platform_name} captions generated from it.
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
    parts = re.split(r"\n(?=\d+\.\s)", raw.strip())
    captions = []
    for part in parts:
        # Strip leading number and whitespace
        clean = re.sub(r"^\d+\.\s*", "", part.strip())
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
    return "\n\n".join(
        f"{i + 1}. {caption}" for i, caption in enumerate(captions)
    )


def strip_urls(text: str) -> str:
    """
    Removes all URLs from a caption string.
    Used before rendering text onto quote card images.
    """
    return re.sub(r"http\S+", "", text).strip()


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

Write ONE new {platform.name} caption in exactly the same style, tone and format as the others. It must cover a different moment from the transcript than the one it is replacing. End it with the same episode link used in the others: {spotify_link}

Return only the new caption text, nothing else. Do not number it.
"""
