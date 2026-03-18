# ============================================================
# Podcast Agent — Shared Utilities
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Shared helper functions and constants used across all
# pipeline scripts.
# Import with: from scripts.utils import format_time, load_metadata
# ============================================================

import json
import os

# ============================================================
# CONSTANTS
# Centralised path reference for the active episode metadata
# file written by fetch.py and read by all downstream scripts.
# ============================================================

METADATA_PATH = "output/metadata.json"

# ============================================================
# TIME FORMATTER
# Converts a duration in seconds to a human-readable string.
# Used by fetch.py, transcribe.py, caption.py, imagegen.py.
# ============================================================

def format_time(seconds):
    """
    Converts a duration in seconds to a human-readable string.

    Returns minutes + seconds format for durations over 60s,
    and seconds-only format for shorter durations.

    Examples:
        254.3  → "4m 14.3s"
        38.45  → "38.45s"
        60.0   → "1m 0.0s"

    Args:
        seconds (float): Duration in seconds.

    Returns:
        str: Formatted time string.
    """
    if seconds >= 60:
        minutes = int(seconds // 60)    # Whole minutes
        secs = round(seconds % 60, 2)  # Remaining seconds
        return f"{minutes}m {secs}s"
    return f"{round(seconds, 2)}s"     # Under a minute — seconds only

# ============================================================
# METADATA LOADER
# Centralised metadata reader used by transcribe.py,
# caption.py and imagegen.py.
#
# Performs three checks in sequence:
#   1. metadata.json exists (fetch.py has been run)
#   2. File is valid and readable JSON
#   3. episode_paths key is present (subfolder was created)
#
# Returns the full metadata dict on success, None on any
# failure — callers should check for None before proceeding.
# ============================================================

def load_metadata():
    # Check 1: metadata.json must exist before attempting to read
    if not os.path.exists(METADATA_PATH):
        print("⚠️  No metadata found. Please run Fetch Episode first.")
        return None

    # Check 2: file must be valid and parseable JSON
    try:
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Could not read metadata file: {e}")
        print("   Try re-running Fetch Episode to regenerate it.")
        return None

    # Check 3: episode_paths must be present for downstream folder access
    if not metadata.get("episode_paths"):
        print("⚠️  Episode folder info missing from metadata.")
        print("   Please re-run Fetch Episode to regenerate it.")
        return None

    return metadata