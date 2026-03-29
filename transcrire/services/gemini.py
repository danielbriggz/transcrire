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
                "Run \'transcrire --check api-keys\' to update it."
            ) from e
        if "404" in err_str:
            raise GeminiError(
                f"Gemini model '{MODEL}' not found. "
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
