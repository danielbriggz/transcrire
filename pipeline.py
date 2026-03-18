# ============================================================
# Podcast Agent — Pipeline Runner
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Runs the full podcast agent pipeline in a single command.
# Supports two modes:
#
#   Full Auto   — smart defaults, no interruptions
#   Guided Auto — configure once upfront, then run
#
# Usage:
#   python pipeline.py
#   python pipeline.py --auto --season 6 --episode 5
#
# All runs are logged to pipeline_run.log.
# Captions generated in pipeline mode are saved with a
# _pending_review suffix — never silently treated as final.
# ============================================================

import os
import sys
import json
import time
import argparse
from datetime import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from scripts.fetch      import fetch_episode, check_new_episodes
from scripts.transcribe import transcribe
from scripts.caption    import generate_captions
from scripts.imagegen   import generate_images
from scripts.utils      import format_time, load_metadata

LOG_PATH = "pipeline_run.log"

# ============================================================
# PIPELINE CONFIG
# Central data structure holding all decision values for a
# single pipeline run. Populated either from smart defaults
# (Full Auto) or from user responses upfront (Guided Auto).
# Passed to each script's core functions to bypass input().
#
# Keys:
#   mode                  : "full_auto" or "guided_auto"
#   podcast_name          : name matching a key in feeds.json
#   season                : int
#   episode               : int
#   fetch_choice          : "1"=audio "2"=art "3"=link "4"=all
#   skip_duplicates       : bool — skip if already in history
#   transcribe_mode       : "groq" or "offline"
#   transcript_type       : "plain", "segments" or "words"
#   caption_platforms     : list e.g. ["twitter", "facebook"]
#   skip_image_review     : bool — skip post-generation review
#   groq_fallback_triggered: bool — set by transcribe.py if needed
# ============================================================

def make_pipeline_config(overrides=None):
    # ---- Full Auto smart defaults ----
    config = {
        "audio_source":           "rss",      # "rss" or "pc"
        "mode":                   "full_auto",
        "podcast_name":           None,
        "season":                 None,
        "episode":                None,
        "fetch_choice":           "4",
        "skip_duplicates":        True,
        "transcribe_mode":        "groq",
        "transcript_type":        "segments",
        "caption_platforms":      ["all"],
        "skip_image_review":      True,
        "groq_fallback_triggered": False,
        "groq_fallback_reason":    None,
    }
    if overrides:
        config.update(overrides)
    return config

# ============================================================
# STAGE RESULT
# Tracks the outcome of each pipeline stage.
# Collected after every stage and used for the end-of-run
# summary and log entries.
#
# status values: "completed", "skipped", "failed"
# ============================================================

def make_stage_result(stage, status, output_paths=None, reason=None):
    return {
        "stage":        stage,
        "status":       status,
        "output_paths": output_paths or [],
        "reason":       reason or "",
        "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

# ============================================================
# LOGGER
# Writes structured, human-readable entries to pipeline_run.log.
# Appends to existing log so all runs are preserved.
# ============================================================

def log(message, indent=0):
    # Write a single line to the log file with optional indentation
    prefix = "  " * indent
    line   = f"{prefix}{message}\n"
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)

def log_run_header(config, run_id):
    # Write the opening header for a new pipeline run
    log("")
    log("=" * 60)
    log(f"PIPELINE RUN — {run_id}")
    log(f"Mode    : {config['mode'].replace('_', ' ').title()}")
    log(f"Podcast : {config.get('podcast_name', 'Not specified')}")
    log(f"Episode : S{config.get('season')}E{config.get('episode')}")
    log(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

def log_stage(result):
    # Write a stage outcome entry to the log
    icon = {"completed": "✅", "skipped": "⚠️ ", "failed": "❌"}.get(result["status"], "  ")
    log(f"\n{icon} {result['stage'].upper()} — {result['status'].upper()}")
    log(f"   Time: {result['timestamp']}", indent=1)
    if result["reason"]:
        log(f"   Reason: {result['reason']}", indent=1)
    if result.get("fallback"):
        # Write Groq fallback as a distinct entry separate from stage result
        log(f"\n   ⚡ GROQ FALLBACK", indent=1)
        log(f"   Reason : {result['fallback']['reason']}", indent=2)
        log(f"   Action : Switched to offline Whisper", indent=2)
        log(f"   Impact : Transcription took significantly longer than expected", indent=2)
    if result["output_paths"]:
        log("   Outputs:", indent=1)
        for path in result["output_paths"]:
            log(f"- {path}", indent=2)

def log_run_footer(results, elapsed, run_id):
    # Write the closing summary for a pipeline run
    completed = sum(1 for r in results if r["status"] == "completed")
    skipped   = sum(1 for r in results if r["status"] == "skipped")
    failed    = sum(1 for r in results if r["status"] == "failed")

    log(f"\n{'=' * 60}")
    log(f"RUN COMPLETE — {run_id}")
    log(f"Duration : {format_time(elapsed)}")
    log(f"Stages   : {completed} completed | {skipped} skipped | {failed} failed")
    log(f"{'=' * 60}\n")

def parse_last_run_duration():
    # ============================================================
    # Parses pipeline_run.log to find the most recently completed
    # run's total duration for estimated run time display.
    # Returns a formatted duration string or None if no log exists
    # or no completed run entry can be found.
    # ============================================================
    if not os.path.exists(LOG_PATH):
        return None

    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all duration entries in the log
        # Format written by log_run_footer: "Duration : Xm Ys" or "Duration : X.Xs"
        import re
        matches = re.findall(r"Duration\s*:\s*(.+)", content)

        if not matches:
            return None

        # Return the most recent duration entry (last match)
        return matches[-1].strip()

    except Exception:
        return None
    
def display_estimated_run_time():
    # ============================================================
    # Displays an estimated run time before the pipeline starts.
    # Based on the most recent completed run duration from
    # pipeline_run.log. Shows a first-run notice if no log exists.
    # ============================================================
    last_duration = parse_last_run_duration()

    if last_duration:
        print(f"\n  ⏱️  Estimated run time: ~{last_duration} (based on last run)")
    else:
        print("\n  ⏱️  First run — no previous duration estimate available.")


def send_completion_notification(config, results, elapsed):
    # ============================================================
    # Sends a Windows toast notification when a pipeline run
    # completes. Only triggered in Full Auto mode since Guided
    # Auto users are already watching the terminal.
    #
    # Falls back to terminal bell if plyer is not installed.
    # Never interrupts the run if notification fails.
    # ============================================================
    if config.get("mode") != "full_auto":
        return

    episode  = f"S{config.get('season')}E{config.get('episode')}"
    complete = sum(1 for r in results if r["status"] == "completed")
    failed   = sum(1 for r in results if r["status"] == "failed")
    status   = "✅ Completed" if not failed else f"⚠️  {failed} stage(s) failed"

    try:
        from plyer import notification
        notification.notify(
            title   = f"🎙️ Podcast Agent — {episode}",
            message = f"{status} in {format_time(elapsed)}",
            timeout = 8,
        )
    except ImportError:
        # plyer not installed — fall back to terminal bell
        print("\a")
    except Exception:
        # Never interrupt the run for a notification failure
        pass


CONFIG_TEMPLATE_PATH = "pipeline_config.json"

# Keys that are runtime-only and should not be saved to the template
RUNTIME_KEYS = {
    "groq_fallback_triggered",
    "groq_fallback_reason",
}

def save_config_template(config):
    # ============================================================
    # Saves the current pipeline config as a reusable template
    # in pipeline_config.json. Strips runtime-only keys before
    # saving so the template stays clean and reusable.
    # ============================================================
    template = {k: v for k, v in config.items() if k not in RUNTIME_KEYS}

    with open(CONFIG_TEMPLATE_PATH, "w") as f:
        json.dump(template, f, indent=2)

    print(f"✅ Config template saved to {CONFIG_TEMPLATE_PATH}")

def load_config_template():
    # ============================================================
    # Loads a previously saved pipeline_config.json template.
    # Returns the config dict or None if file doesn't exist
    # or cannot be parsed.
    # ============================================================
    if not os.path.exists(CONFIG_TEMPLATE_PATH):
        return None

    try:
        with open(CONFIG_TEMPLATE_PATH, "r") as f:
            template = json.load(f)
        # Restore runtime keys to their default values
        template["groq_fallback_triggered"] = False
        template["groq_fallback_reason"]    = None
        return template
    except Exception:
        print("⚠️  Could not load pipeline_config.json — file may be corrupted.")
        return None


# ============================================================
# PODCAST SELECTOR
# Used in both modes to select a podcast from feeds.json.
# In Full Auto: uses first saved podcast if only one exists,
# otherwise prompts once for selection before run begins.
# In Guided Auto: presented as part of the decision map.
# ============================================================

def select_podcast():
    feeds_path = "feeds.json"

    if not os.path.exists(feeds_path):
        print("⚠️  No saved podcasts found.")
        print("   Run the interactive Fetch Episode first to save a feed.")
        return None

    with open(feeds_path, "r") as f:
        feeds = json.load(f)

    if not feeds:
        print("⚠️  No saved podcasts found.")
        print("   Run the interactive Fetch Episode first to save a feed.")
        return None

    feed_list = list(feeds.keys())

    feed_list = list(feeds.keys())

    # ---- Always show full list with add option ----
    print("\nSaved podcasts:")
    for i, name in enumerate(feed_list, 1):
        print(f"  {i}. {name}")
    print("  0. Add new podcast")

    choice = input("Select a podcast: ").strip()

    if choice == "0":
        # ---- Add new RSS feed ----
        import feedparser
        rss_url = input("Enter RSS feed URL: ").strip()
        try:
            feed     = feedparser.parse(rss_url)
            new_name = feed.feed.get("title", "Unknown Podcast")
        except Exception:
            print("⚠️  Could not read the RSS feed. Check the URL and your internet connection.")
            return None

        feeds[new_name] = rss_url
        with open(feeds_path, "w") as f:
            json.dump(feeds, f, indent=2)
        print(f"✅ Saved '{new_name}' for future use.")
        return new_name

    elif choice.isdigit() and 1 <= int(choice) <= len(feed_list):
        chosen = feed_list[int(choice) - 1]
        print(f"Using: {chosen}")
        return chosen

    print("⚠️  Invalid selection.")
    return None

# ============================================================
# EPISODE VALIDATOR
# Checks the RSS feed for the requested season/episode before
# the pipeline begins. Returns the episode title on success
# or None on failure — triggers hard stop in the caller.
# ============================================================

def validate_episode(config):
    import feedparser

    feeds_path = "feeds.json"
    if not os.path.exists(feeds_path):
        return None

    with open(feeds_path, "r") as f:
        feeds = json.load(f)

    podcast_name = config.get("podcast_name")
    if podcast_name not in feeds:
        return None

    rss_url = feeds[podcast_name]

    try:
        feed    = feedparser.parse(rss_url)
        season  = config.get("season")
        episode = config.get("episode")

        for entry in feed.entries:
            entry_season  = int(entry.get("itunes_season", 0))
            entry_episode = int(entry.get("itunes_episode", 0))
            if entry_season == season and entry_episode == episode:
                return entry.title

        return None

    except Exception:
        return None

# ============================================================
# DUPLICATE CHECKER
# Checks history.json for the requested episode before run.
# Returns True if the episode should be skipped.
# Behaviour varies by mode — set via config["skip_duplicates"].
# ============================================================

def check_pipeline_duplicate(config):
    history_path = "history.json"
    if not os.path.exists(history_path):
        return False

    with open(history_path, "r") as f:
        history = json.load(f)

    season  = config.get("season")
    episode = config.get("episode")

    duplicates = [
        e for e in history
        if e.get("season") == season and e.get("episode") == episode
    ]

    if not duplicates:
        return False

    # Format duplicate info for display
    for e in duplicates:
        print(f"⚠️  S{season}E{episode} was already processed on {e.get('date')}: {e.get('title')}")

    if config.get("skip_duplicates", True):
        print("   Skipping — duplicate processing disabled in this mode.")
        return True

    # Guided Auto pre-approved proceeding
    print("   Proceeding as configured.")
    return False

# ============================================================
# PENDING REVIEW BACKLOG WARNING
# Checks the active episode's captions folder for any
# existing _pending_review files from previous pipeline runs.
# Warns the user before the new run begins.
# ============================================================

def scan_pending_review_backlog():
    # ============================================================
    # Scans ALL episode subfolders under output/ for any
    # _pending_review caption files — not just the active episode.
    # Returns a dict mapping episode folder name to list of
    # pending files found within it.
    # ============================================================
    output_dir = "output"
    backlog    = {}

    if not os.path.exists(output_dir):
        return backlog

    for item in os.listdir(output_dir):
        episode_path   = os.path.join(output_dir, item)
        captions_folder = os.path.join(episode_path, "captions")

        if not os.path.isdir(captions_folder):
            continue

        pending = [
            f for f in os.listdir(captions_folder)
            if "_pending_review" in f
        ]

        if pending:
            backlog[item] = pending

    return backlog

def check_pending_review_backlog():
    # ============================================================
    # Checks the full output/ tree for pending review files.
    # Groups results by episode and displays them clearly.
    # Prompts user to continue or cancel before the run starts.
    # ============================================================
    backlog = scan_pending_review_backlog()

    if not backlog:
        return

    total = sum(len(files) for files in backlog.values())

    print(f"\n⚠️  {total} caption file(s) across {len(backlog)} episode(s) are pending review:\n")
    for episode, files in backlog.items():
        print(f"   📁 {episode}")
        for f in files:
            print(f"      - {f}")

    print("\n   Review them before running again.")
    proceed = input("   Continue anyway? (y/n): ").strip().lower()
    if proceed != "y":
        print("Pipeline cancelled.")
        sys.exit()

# ============================================================
# FULL AUTO CONFIG
# Populates PipelineConfig with smart defaults.
# Only prompts for the absolute minimum — podcast, season
# and episode — everything else is pre-decided.
# ============================================================

def build_full_auto_config(season=None, episode=None, podcast_name=None):
    print("\n" + "=" * 40)
    print("     🤖  FULL AUTO MODE")
    print("=" * 40)
    print("Smart defaults will be used for all decisions.")
    print("Captions will be saved as pending review.\n")

    # Select podcast if not passed via CLI
    if not podcast_name:
        podcast_name = select_podcast()
        if not podcast_name:
            return None

    # Get season and episode if not passed via CLI
    if not season:
        season = input("Enter season number: ").strip()
        if not season.isdigit():
            print("⚠️  Invalid season number.")
            return None
        season = int(season)

    if not episode:
        episode = input("Enter episode number: ").strip()
        if not episode.isdigit():
            print("⚠️  Invalid episode number.")
            return None
        episode = int(episode)

    return make_pipeline_config({
        "mode":         "full_auto",
        "podcast_name": podcast_name,
        "season":       season,
        "episode":      episode,
    })

# ============================================================
# GUIDED AUTO CONFIG
# Walks the user through every decision point upfront.
# Pipeline runs uninterrupted after configuration is complete.
# ============================================================

def check_internet():
    # ============================================================
    # Quick internet connectivity check used by pre-flight
    # validation. Attempts to reach Google's DNS server.
    # Returns True if reachable, False otherwise.
    # ============================================================
    import socket
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False
    
def preflight_validation(config):
    # ============================================================
    # Runs after build_guided_auto_config() to validate each
    # configured value against actual system state.
    # Corrects issues automatically where possible, otherwise
    # warns the user before the run begins.
    #
    # Checks:
    #   - Groq configured but no internet → switch to offline
    #   - API keys present in config.py
    #   - Audio will be downloadable (feed reachable)
    # ============================================================
    print("\nRunning pre-flight checks...")
    warnings = []

    # ---- Check 1: Groq requires internet ----
    if config.get("transcribe_mode") == "groq":
        if not check_internet():
            print("⚠️  No internet connection detected.")
            print("   Groq transcription is not available — switching to offline Whisper.")
            config["transcribe_mode"]     = "offline"
            config["groq_fallback_triggered"] = True
            config["groq_fallback_reason"]    = "no_internet"
            warnings.append("Transcription mode switched from Groq to offline (no internet).")

    # ---- Check 2: Gemini API key present ----
    try:
        from config import GEMINI_API_KEY
        if not GEMINI_API_KEY or "placeholder" in GEMINI_API_KEY.lower():
            warnings.append("GEMINI_API_KEY not set — caption generation may fail.")
            print("⚠️  GEMINI_API_KEY appears to be missing or invalid.")
    except ImportError:
        warnings.append("Could not read config.py — API keys unverified.")

    # ---- Check 3: Groq API key present (if applicable) ----
    if config.get("transcribe_mode") == "groq":
        try:
            from config import GROQ_API_KEY
            if not GROQ_API_KEY or "placeholder" in GROQ_API_KEY.lower():
                warnings.append("GROQ_API_KEY not set — switching to offline transcription.")
                print("⚠️  GROQ_API_KEY appears to be missing. Switching to offline Whisper.")
                config["transcribe_mode"] = "offline"
        except ImportError:
            pass

    if not warnings:
        print("✅ Pre-flight checks passed.")
    else:
        print(f"\n   {len(warnings)} warning(s) noted — pipeline will proceed with adjustments.")

    return config

def build_guided_auto_config():
    print("\n" + "=" * 40)
    print("     🎛️   GUIDED AUTO MODE")
    print("=" * 40)
    print("Answer the following questions once.")
    print("The pipeline will then run without interruption.\n")

    config = make_pipeline_config({"mode": "guided_auto"})

    # ---- Podcast ----
    podcast_name = select_podcast()
    if not podcast_name:
        return None
    config["podcast_name"] = podcast_name

    # ---- Episode ----
    season = input("\nEnter season number: ").strip()
    if not season.isdigit():
        print("⚠️  Invalid season number.")
        return None
    config["season"] = int(season)

    episode = input("Enter episode number: ").strip()
    if not episode.isdigit():
        print("⚠️  Invalid episode number.")
        return None
    config["episode"] = int(episode)

    # ---- Fetch ----
    print("\nWhat would you like to fetch?")
    print("  1. Audio only")
    print("  2. Cover art only")
    print("  3. Spotify link only")
    print("  4. All (recommended)")
    fetch_choice = input("Enter 1, 2, 3 or 4 (default 4): ").strip() or "4"
    config["fetch_choice"] = fetch_choice

    # ---- Duplicate handling ----
    print("\nIf this episode has already been processed:")
    print("  1. Skip it (default)")
    print("  2. Process it again")
    dup_choice = input("Enter 1 or 2 (default 1): ").strip() or "1"
    config["skip_duplicates"] = dup_choice != "2"

    # ---- Transcription mode ----
    print("\nTranscription mode:")
    print("  1. Fast — Groq API (requires internet, default)")
    print("  2. Offline — Whisper small (no internet needed)")
    trans_mode = input("Enter 1 or 2 (default 1): ").strip() or "1"
    config["transcribe_mode"] = "groq" if trans_mode == "1" else "offline"

    # ---- Transcript type ----
    print("\nTranscript type:")
    print("  1. Plain text")
    print("  2. Segment level timestamps (default)")
    print("  3. Word level timestamps")
    type_choice = input("Enter 1, 2 or 3 (default 2): ").strip() or "2"
    config["transcript_type"] = {
        "1": "plain", "2": "segments", "3": "words"
    }.get(type_choice, "segments")

    # ---- Caption platforms ----
    print("\nGenerate captions for:")
    print("  1. All platforms (default)")
    print("  2. Twitter only")
    print("  3. LinkedIn only")
    print("  4. Facebook only")
    print("  5. Twitter + Facebook")
    plat_choice = input("Enter 1-5 (default 1): ").strip() or "1"
    config["caption_platforms"] = {
        "1": ["all"],
        "2": ["twitter"],
        "3": ["linkedin"],
        "4": ["facebook"],
        "5": ["twitter", "facebook"],
    }.get(plat_choice, ["all"])

    # ---- Image review ----
    print("\nAfter images are generated:")
    print("  1. Skip review — keep all (default)")
    print("  2. Review images after generation")
    review_choice = input("Enter 1 or 2 (default 1): ").strip() or "1"
    config["skip_image_review"] = review_choice != "2"

    # ---- Summary ----
    print("\n" + "-" * 40)
    print("Configuration summary:")
    print(f"  Podcast     : {config['podcast_name']}")
    print(f"  Episode     : S{config['season']}E{config['episode']}")
    print(f"  Fetch       : {config['fetch_choice']}")
    print(f"  Transcribe  : {config['transcribe_mode']} / {config['transcript_type']}")
    print(f"  Captions    : {', '.join(config['caption_platforms'])}")
    print(f"  Duplicates  : {'skip' if config['skip_duplicates'] else 'proceed'}")
    print(f"  Image review: {'skip' if config['skip_image_review'] else 'review'}")
    print("-" * 40)
    confirm = input("\nProceed with these settings? (y/n): ").strip().lower()
    if confirm != "y":
        print("Pipeline cancelled.")
        return None

    # Run pre-flight validation after user confirms
    # May adjust config values (e.g. Groq → offline) before run starts
    config = preflight_validation(config)

    # ---- Offer to save as reusable template ----
    save_choice = input("\nSave these settings as a reusable template? (y/n): ").strip().lower()
    if save_choice == "y":
        save_config_template(config)

    return config

# ============================================================
# END-OF-RUN SUMMARY
# Prints a formatted table of all stage outcomes to the
# terminal after every pipeline run.
# ============================================================

def print_summary(results, elapsed, config):
    print("\n" + "=" * 40)
    print("     📊  PIPELINE SUMMARY")
    print("=" * 40)

    print(f"\n  Episode : S{config.get('season')}E{config.get('episode')}")
    print(f"  Mode    : {config.get('mode', '').replace('_', ' ').title()}")
    print(f"  Duration: {format_time(elapsed)}")

    # ---- Compare actual vs estimated duration ----
    last_duration = parse_last_run_duration()
    if last_duration:
        print(f"  Estimate: ~{last_duration} (previous run)")

    print("-" * 40)

    icons = {"completed": "✅", "skipped": "⚠️ ", "failed": "❌"}
    for result in results:
        icon   = icons.get(result["status"], "  ")
        reason = f" — {result['reason']}" if result["reason"] else ""
        print(f"  {icon} {result['stage'].capitalize()}{reason}")
        for path in result["output_paths"]:
            print(f"       → {path}")

    # ---- Groq fallback notice ----
    if config.get("groq_fallback_triggered"):
        reason_messages = {
            "file_too_large":  "Audio file was too large for Groq even after compression.",
            "groq_api_failure": "Groq API call failed.",
            "no_internet":     "No internet connection was available at launch.",
        }
        reason = reason_messages.get(
            config.get("groq_fallback_reason", ""),
            "Groq was unavailable."
        )
        print(f"\n  ⚡ GROQ FALLBACK")
        print(f"     Reason : {reason}")
        print(f"     Action : Transcription ran offline via Whisper.")
        print(f"     Impact : Run took significantly longer than a Groq-based run would have.")

    # ---- Pending review notice ----
    pending_stages = [r for r in results if r["status"] == "completed" and "caption" in r["stage"]]
    if pending_stages:
        print("\n  ℹ️   Captions saved as _pending_review — review before posting.")

    print("=" * 40)
    print(f"\nFull log saved to: {LOG_PATH}")

# ============================================================
# PIPELINE RUNNER
# Executes each stage in sequence using the populated config.
# Collects StageResult after every stage.
# Handles hard stops and skippable failures.
# ============================================================

def run_pipeline(config):
    run_id   = datetime.now().strftime("%Y%m%d-%H%M%S")
    results  = []
    start    = time.time()

    log_run_header(config, run_id)

    # ---- Estimated run time ----
    display_estimated_run_time()

    # ---- Pre-run checks ----
    # Pending review and episode validation only apply to RSS runs
    if config.get("audio_source") != "pc":

        # Check for pending review backlog
        check_pending_review_backlog()

        # Validate episode exists in RSS feed before doing anything
        print(f"\nValidating episode S{config['season']}E{config['episode']}...")
        episode_title = validate_episode(config)
        if not episode_title:
            reason = f"S{config['season']}E{config['episode']} not found in RSS feed."
            result = make_stage_result("validation", "failed", reason=reason)
            results.append(result)
            log_stage(result)
            log_run_footer(results, time.time() - start, run_id)
            print(f"\n❌ {reason}")
            print("   Check the season and episode numbers and try again.")
            return results

        print(f"✅ Found: {episode_title}")

        # Check for duplicate episode — only skip if confirmed in history
        if check_pipeline_duplicate(config):
            reason = f"S{config['season']}E{config['episode']} already in history — skipped."
            result = make_stage_result("fetch", "skipped", reason=reason)
            results.append(result)
            log_stage(result)
            log_run_footer(results, time.time() - start, run_id)
            print_summary(results, time.time() - start, config)
            return results

    # ---- Stage 1: Fetch ----
    # Skipped entirely when audio source is PC upload
    if config.get("audio_source") == "pc":
        result = make_stage_result("fetch", "skipped", reason="Audio source is PC upload — fetch not required.")
        results.append(result)
        log_stage(result)
    else:
        print("\n" + "-" * 40)
        print("STAGE 1 — FETCH EPISODE")
        print("-" * 40)
    try:
        metadata = fetch_episode(config)
        if not metadata:
            result = make_stage_result("fetch", "failed", reason="fetch_episode() returned no metadata.")
            results.append(result)
            log_stage(result)
            # Fetch failure is critical — cannot continue without audio
            log_run_footer(results, time.time() - start, run_id)
            print_summary(results, time.time() - start, config)
            return results

        fetch_notes = []
        if not metadata.get("spotify_link"):
            fetch_notes.append("No Spotify link found in feed.")
        # Cover art absence is non-critical — logged but doesn't fail fetch
        images_folder = metadata.get("episode_paths", {}).get("images", "")
        cover_files   = [
            f for f in os.listdir(images_folder)
            if f.endswith(("_cover.jpg", "_cover.png"))
        ] if os.path.exists(images_folder) else []
        if not cover_files:
            fetch_notes.append("No episode cover art found in feed — image generation may be affected.")

        result = make_stage_result(
            "fetch", "completed",
            output_paths=[metadata.get("episode_paths", {}).get("root", "")],
            reason=", ".join(fetch_notes) if fetch_notes else ""
        )
        results.append(result)
        log_stage(result)

    except Exception as e:
        result = make_stage_result("fetch", "failed", reason=str(e))
        results.append(result)
        log_stage(result)
        log_run_footer(results, time.time() - start, run_id)
        print_summary(results, time.time() - start, config)
        return results

    # ---- Stage 2: Transcribe ----
    print("\n" + "-" * 40)
    print("STAGE 2 — TRANSCRIBE")
    print("-" * 40)
    try:
        transcript_path = transcribe(config)
        if not transcript_path:
            result = make_stage_result("transcribe", "failed", reason="Transcription produced no output.")
            results.append(result)
            log_stage(result)
            # Transcription failure is critical — cannot caption without transcript
            log_run_footer(results, time.time() - start, run_id)
            print_summary(results, time.time() - start, config)
            return results

        # Check if Groq fallback was triggered during transcription
        fallback_info = None
        if config.get("groq_fallback_triggered"):
            fallback_info = {
                "reason": config.get("groq_fallback_reason", "unknown"),
            }

        result = make_stage_result(
            "transcribe", "completed",
            output_paths=[transcript_path],
            reason="Groq fallback triggered — ran offline." if fallback_info else ""
        )
        # Attach fallback details for distinct log entry
        result["fallback"] = fallback_info
        results.append(result)
        log_stage(result)

    except Exception as e:
        result = make_stage_result("transcribe", "failed", reason=str(e))
        results.append(result)
        log_stage(result)
        log_run_footer(results, time.time() - start, run_id)
        print_summary(results, time.time() - start, config)
        return results

    # ---- Stage 3: Captions ----
    # Skipped when audio source is PC upload
    if config.get("audio_source") == "pc":
        result = make_stage_result("captions", "skipped", reason="PC upload source — captions reserved for RSS episodes.")
        results.append(result)
        log_stage(result)
    else:
        print("\n" + "-" * 40)
        print("STAGE 3 — CREATE CAPTIONS")
        print("-" * 40)
    try:
        caption_paths = generate_captions(config)
        if not caption_paths:
            result = make_stage_result("captions", "failed", reason="No captions were generated.")
            results.append(result)
            log_stage(result)
        else:
            # Some platforms may have failed — partial success is still completed
            partial_note = ""
            expected     = len(config.get("caption_platforms", ["all"]))
            actual       = len(caption_paths)
            if expected != actual and "all" not in config.get("caption_platforms", ["all"]):
                partial_note = f"{actual} of {expected} platform(s) generated successfully."
            result = make_stage_result(
                "captions", "completed",
                output_paths=caption_paths,
                reason=partial_note
            )
            results.append(result)
            log_stage(result)

    except Exception as e:
        result = make_stage_result("captions", "failed", reason=str(e))
        results.append(result)
        log_stage(result)

    # ---- Stage 4: Images ----
    # Skipped when audio source is PC upload
    if config.get("audio_source") == "pc":
        result = make_stage_result("images", "skipped", reason="PC upload source — images reserved for RSS episodes.")
        results.append(result)
        log_stage(result)
    else:
        print("\n" + "-" * 40)
        print("STAGE 4 — GENERATE IMAGES")
        print("-" * 40)
    try:
        image_paths = generate_images(config)
        if not image_paths:
            result = make_stage_result("images", "skipped", reason="No images were generated.")
            results.append(result)
            log_stage(result)
        else:
            result = make_stage_result("images", "completed", output_paths=image_paths)
            results.append(result)
            log_stage(result)

    except Exception as e:
        result = make_stage_result("images", "failed", reason=str(e))
        results.append(result)
        log_stage(result)

    # ---- End of run ----
    elapsed = round(time.time() - start, 2)
    log_run_footer(results, elapsed, run_id)
    print_summary(results, elapsed, config)

    # ---- Completion notification (Full Auto only) ----
    send_completion_notification(config, results, elapsed)

    # ---- Post-run backlog check ----
    # Re-scan entire output/ folder and report total pending review count
    backlog = scan_pending_review_backlog()
    if backlog:
        total = sum(len(files) for files in backlog.values())
        print(f"\n  📋 {total} caption file(s) across {len(backlog)} episode(s) are awaiting review.")
        print("     Run 'python pipeline.py --review' to see the full list.")

    return results

def review_pending_captions():
    # ============================================================
    # Interactive review flow for _pending_review caption files.
    # Lists all pending files grouped by episode and allows the
    # user to mark individual files as reviewed — renaming them
    # by removing the _pending_review suffix.
    #
    # Called from the pipeline menu when pending files exist.
    # ============================================================
    backlog = scan_pending_review_backlog()

    if not backlog:
        print("\n✅ No pending review caption files found.")
        return

    total = sum(len(files) for files in backlog.values())
    print(f"\n📋 {total} caption file(s) pending review:\n")

    # ---- Build a flat numbered list for selection ----
    # Each entry stores episode folder, filename and full path
    items = []
    for episode, files in backlog.items():
        for f in files:
            captions_folder = os.path.join("output", episode, "captions")
            full_path       = os.path.join(captions_folder, f)
            items.append({
                "episode":  episode,
                "filename": f,
                "path":     full_path,
            })

    for i, item in enumerate(items, 1):
        print(f"  {i}. [{item['episode']}]")
        print(f"     {item['filename']}")

    print("\n  Options:")
    print("  A. Mark all as reviewed")
    print("  Enter a number to mark one file as reviewed")
    print("  0. Back to menu")

    while True:
        choice = input("\nEnter choice: ").strip()

        if choice == "0":
            return

        elif choice.upper() == "A":
            # ---- Mark all as reviewed ----
            marked = 0
            for item in items:
                new_name = item["filename"].replace("_pending_review", "")
                new_path = os.path.join(os.path.dirname(item["path"]), new_name)
                try:
                    os.rename(item["path"], new_path)
                    print(f"  ✅ Marked as reviewed: {new_name}")
                    marked += 1
                except Exception as e:
                    print(f"  ⚠️  Could not rename {item['filename']}: {e}")
            print(f"\n{marked} file(s) marked as reviewed.")
            return

        elif choice.isdigit() and 1 <= int(choice) <= len(items):
            # ---- Mark single file as reviewed ----
            item     = items[int(choice) - 1]
            new_name = item["filename"].replace("_pending_review", "")
            new_path = os.path.join(os.path.dirname(item["path"]), new_name)
            try:
                os.rename(item["path"], new_path)
                print(f"\n✅ Marked as reviewed: {new_name}")
                # Refresh list after marking
                items.pop(int(choice) - 1)
                if not items:
                    print("All files reviewed.")
                    return
                # Reprint updated list
                print(f"\n{len(items)} file(s) remaining:\n")
                for i, item in enumerate(items, 1):
                    print(f"  {i}. [{item['episode']}]")
                    print(f"     {item['filename']}")
            except Exception as e:
                print(f"⚠️  Could not rename file: {e}")

        else:
            print("⚠️  Invalid choice.")

# ============================================================
# MAIN
# Entry point for pipeline.py.
# Handles CLI arguments for Full Auto inline invocation,
# then presents mode selection if not specified.
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Podcast Agent Pipeline Runner")
    parser.add_argument("--auto",    action="store_true", help="Run in Full Auto mode")
    parser.add_argument("--season",  type=int,            help="Season number")
    parser.add_argument("--episode", type=int,            help="Episode number")
    parser.add_argument("--podcast", type=str,            help="Podcast name (must match feeds.json)")
    parser.add_argument("--review",  action="store_true", help="List all pending review caption files")
    parser.add_argument("--config",  action="store_true", help="Load saved pipeline_config.json template")
    args = parser.parse_args()

#    # ---- Audio source selection ----
#     # Asked before mode selection — determines which stages run
#     print("\nSelect audio source:")
#     print("  1. 💻  Upload from PC      (transcription only)")
#     print("  2. 📡  Podcast RSS         (full pipeline)")
#     print("  0.     Cancel")
#     source_choice = input("\nEnter choice: ").strip()

#     if source_choice == "0":
#         print("Pipeline cancelled.")
#         return
#     elif source_choice == "1":
#         audio_source = "pc"
#     elif source_choice == "2":
#         audio_source = "rss"
#     else:
#         print("⚠️  Invalid choice.")
#         return

    # ---- Review flag — list all pending review files ----
    if args.review:
        review_pending_captions()
        return

    # ---- Load saved config template ----
    if args.config:
        template = load_config_template()
        if not template:
            print("⚠️  No saved config template found. Run Guided Auto first to create one.")
            sys.exit(1)
        print(f"\n✅ Loaded config template:")
        print(f"   Podcast  : {template.get('podcast_name')}")
        print(f"   Mode     : {template.get('mode', '').replace('_', ' ').title()}")
        print(f"   Transcribe: {template.get('transcribe_mode')} / {template.get('transcript_type')}")
        print(f"   Platforms: {', '.join(template.get('caption_platforms', []))}")
        season  = args.season  or int(input("\nEnter season number: ").strip())
        episode = args.episode or int(input("Enter episode number: ").strip())
        template["season"]  = season
        template["episode"] = episode
        run_pipeline(template)
        return

    # ---- CLI Full Auto shortcut ----
    if args.auto:
        config = build_full_auto_config(
            season       = args.season,
            episode      = args.episode,
            podcast_name = args.podcast
        )
        if not config:
            sys.exit(1)
        run_pipeline(config)
        return

    while True:
        # ---- Outer loop: audio source selection ----
        print("\nSelect audio source:")
        print("  1. 💻  Upload from PC      (transcription only)")
        print("  2. 📡  Podcast RSS         (full pipeline)")
        print("  0.     Cancel")
        source_choice = input("\nEnter choice: ").strip()

        if source_choice == "0":
            print("\nGoodbye! 👋")
            return
        elif source_choice == "1":
            audio_source = "pc"
        elif source_choice == "2":
            audio_source = "rss"
        else:
            print("⚠️  Invalid choice.")
            continue

        # ---- Check for pending review backlog before showing inner menu ----
        backlog       = scan_pending_review_backlog()
        pending_count = sum(len(files) for files in backlog.values())

        while True:
            # ---- Build dynamic menu based on audio source ----
            print("\n" + "=" * 40)
            print("     🎙️  PODCAST AGENT PIPELINE")
            print("=" * 40)

            if audio_source == "pc":
                # PC upload — transcription only, no mode selection needed
                print("  💻  PC Upload — Transcription Only")
                print("\n  1. Fast (Groq API — requires internet)")
                print("  2. Offline (Whisper small — no internet)")
            else:
                print("  1. Full Auto    — smart defaults, no interruptions")
                print("  2. Guided Auto  — configure once, then run")

            # Only show saved template option if pipeline_config.json exists
            template_exists = os.path.exists(CONFIG_TEMPLATE_PATH)
            if template_exists:
                template_data = load_config_template()
                print(f"\n  T.  Use saved template ({template_data.get('podcast_name', 'Unknown')} — {template_data.get('transcribe_mode', '')} / {template_data.get('transcript_type', '')})")

            # Only show review option when pending files exist
            if pending_count > 0:
                print(f"\n  R.  📋 Review pending captions ({pending_count} file(s) awaiting review)")

            print("\n  0.  Cancel")
            print("=" * 40)

            choice = input("\nEnter choice: ").strip()

            if choice == "0":
                # Return to audio source selection
                break

            elif audio_source == "pc":
                # ---- PC Upload — transcription only ----
                import shutil

                transcribe_mode = "groq" if choice == "1" else "offline"
                print(f"\n--- PC Upload Transcription ({transcribe_mode.title()}) ---")

                # ---- Step 1: Prompt for file path ----
                print("\nPaste the full path to your audio file:")
                print("(Supported formats: .mp3, .wav, .m4a)\n")
                raw_path = input("File path: ").strip().strip('"')

                if not raw_path:
                    print("⚠️  No file path provided.")
                    continue

                if not os.path.exists(raw_path):
                    print(f"⚠️  File not found: {raw_path}")
                    continue

                if not raw_path.lower().endswith(('.mp3', '.wav', '.m4a')):
                    print("⚠️  Unsupported format. Please use .mp3, .wav or .m4a")
                    continue

                # ---- Step 2: Copy to temporary input/ location ----
                filename    = os.path.basename(raw_path)
                temp_path   = os.path.join("input", f"_temp_{filename}")

                try:
                    shutil.copy2(raw_path, temp_path)
                    print(f"\n✅ File loaded: {filename}")
                except Exception as e:
                    print(f"⚠️  Could not load file: {e}")
                    continue

                # ---- Step 3: Choose transcript type ----
                print("\nTranscript type:")
                print("  1. Plain text (no timestamps)")
                print("  2. Segment level (timestamped by phrase)")
                print("  3. Word level (timestamped by word)")
                type_choice = input("Enter 1, 2 or 3 (default 2): ").strip() or "2"
                transcript_type = {
                    "1": "plain",
                    "2": "segments",
                    "3": "words"
                }.get(type_choice, "segments")

                # ---- Step 4: Transcribe from temp location ----
                pc_config = {
                    "audio_filename":          f"_temp_{filename}",
                    "transcribe_mode":         transcribe_mode,
                    "transcript_type":         transcript_type,
                    "audio_source":            "pc",
                    "groq_fallback_triggered": False,
                    "groq_fallback_reason":    None,
                }

                output_path = transcribe(pc_config)

                # ---- Step 5: Delete temporary file ----
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                        print(f"\n🗑️  Temporary file removed.")
                except Exception as e:
                    print(f"⚠️  Could not remove temporary file: {e}")

                # ---- Step 6: Prompt to save transcript ----
                if output_path:
                    print(f"\n✅ Transcript saved to: {output_path}")
                    print("\nWould you like to copy the transcript to a different location?")
                    print("  1. Yes — specify a folder")
                    print("  2. No  — keep it where it is")
                    save_choice = input("Enter 1 or 2: ").strip()

                    if save_choice == "1":
                        dest_folder = input("Paste destination folder path: ").strip().strip('"')
                        try:
                            os.makedirs(dest_folder, exist_ok=True)
                            dest_path = os.path.join(dest_folder, os.path.basename(output_path))
                            shutil.copy2(output_path, dest_path)
                            print(f"✅ Transcript also copied to: {dest_path}")
                        except Exception as e:
                            print(f"⚠️  Could not copy transcript: {e}")
                else:
                    print("⚠️  Transcription did not complete.")

                # Refresh pending count after run
                backlog       = scan_pending_review_backlog()
                pending_count = sum(len(files) for files in backlog.values())

            elif choice == "1":
                # ---- Full Auto — RSS ----
                config = build_full_auto_config(
                    season       = args.season,
                    episode      = args.episode,
                    podcast_name = args.podcast
                )
                if not config:
                    sys.exit(1)
                config["audio_source"] = "rss"
                run_pipeline(config)
                backlog       = scan_pending_review_backlog()
                pending_count = sum(len(files) for files in backlog.values())

            elif choice == "2":
                # ---- Guided Auto — RSS ----
                config = build_guided_auto_config()
                if not config:
                    sys.exit(1)
                config["audio_source"] = "rss"
                run_pipeline(config)
                backlog       = scan_pending_review_backlog()
                pending_count = sum(len(files) for files in backlog.values())

            elif choice.upper() == "T" and os.path.exists(CONFIG_TEMPLATE_PATH):
                template = load_config_template()
                if not template:
                    print("⚠️  Could not load template.")
                    continue
                season  = int(input("\nEnter season number: ").strip())
                episode = int(input("Enter episode number: ").strip())
                template["season"]  = season
                template["episode"] = episode
                run_pipeline(template)
                # Refresh pending count after run
                backlog       = scan_pending_review_backlog()
                pending_count = sum(len(files) for files in backlog.values())

            elif choice.upper() == "R" and pending_count > 0:
                review_pending_captions()
                # Refresh pending count after review
                backlog       = scan_pending_review_backlog()
                pending_count = sum(len(files) for files in backlog.values())

            else:
                print("⚠️  Invalid choice.")

main()