# ============================================================
# Podcast Agent — Episode Fetcher
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Handles all episode asset retrieval from RSS feeds.
# Manages podcast feed storage, episode history tracking,
# per-episode subfolder creation, and metadata saving.
#
# Fetches any combination of:
#   - Episode audio (downloaded to input/)
#   - Episode cover art (saved to episode images subfolder)
#   - Spotify episode link (saved to metadata.json)
#
# RSS feeds are saved persistently in feeds.json so they
# don't need to be re-entered on every run.
# Episode history is logged in history.json with duplicate
# detection to prevent reprocessing the same episode.
# ============================================================

import json
import feedparser
import requests
import time
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import INPUT_FOLDER, IMAGES_FOLDER
from scripts.utils import format_time

# Path to episode processing history log
HISTORY_PATH = "history.json"

# Path to active episode metadata — read by all downstream scripts
METADATA_PATH = "output/metadata.json"

# ============================================================
# FEED LOADER
# Manages the feeds.json store of saved RSS feeds.
# On first run: prompts for RSS URL, fetches podcast name
# automatically from the feed, and saves for future use.
# On subsequent runs: lists saved podcasts for quick selection.
# Returns both the parsed feed object and podcast name.
# ============================================================

def load_feed(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Uses config["podcast_name"] to select a saved feed
    #     directly without prompting
    #   - If podcast not found in feeds.json, fails with a clear
    #     message rather than prompting for a new URL
    # When called interactively (config=None):
    #   - Original behaviour — shows saved list or prompts for new
    # ============================================================
    feeds_path = "feeds.json"

    if os.path.exists(feeds_path):
        with open(feeds_path, "r") as f:
            feeds = json.load(f)
    else:
        feeds = {}

    # ---- Pipeline mode ----
    if config is not None:
        podcast_name = config.get("podcast_name")
        if not podcast_name:
            print("⚠️  No podcast name specified in pipeline config.")
            return None
        if podcast_name not in feeds:
            print(f"⚠️  Podcast '{podcast_name}' not found in feeds.json.")
            print("   Run the interactive Fetch Episode first to save the feed.")
            return None
        rss_url = feeds[podcast_name]
        try:
            feed = feedparser.parse(rss_url)
        except Exception:
            print("⚠️  Could not load the RSS feed. Check your internet connection.")
            return None
        print(f"Using podcast: {podcast_name}")
        return feed, podcast_name

    # ---- Interactive mode — original behaviour ----
    if feeds:
        print("\nSaved podcasts:")
        feed_list = list(feeds.items())
        for i, (name, url) in enumerate(feed_list):
            print(f"  {i + 1}. {name}")
        print("  0. Add new podcast")
        choice = input("Select a podcast: ").strip()

        if choice == "0":
            rss_url = input("Enter RSS feed URL: ").strip()
            try:
                feed = feedparser.parse(rss_url)
                podcast_name = feed.feed.get("title", "Unknown Podcast")
            except Exception:
                print("⚠️  Could not read the RSS feed. Check the URL and your internet connection.")
                return None
            feeds[podcast_name] = rss_url
            with open(feeds_path, "w") as f:
                json.dump(feeds, f, indent=2)
            print(f"Saved '{podcast_name}' for future use.")
        else:
            try:
                podcast_name, rss_url = feed_list[int(choice) - 1]
            except (ValueError, IndexError):
                print("⚠️  Invalid selection.")
                return None
            print(f"Using: {podcast_name}")
            try:
                feed = feedparser.parse(rss_url)
            except Exception:
                print("⚠️  Could not load the RSS feed. Check your internet connection.")
                return None
    else:
        print("No saved podcasts yet.")
        rss_url = input("Enter RSS feed URL: ").strip()
        try:
            feed = feedparser.parse(rss_url)
            podcast_name = feed.feed.get("title", "Unknown Podcast")
        except Exception:
            print("⚠️  Could not read the RSS feed. Check the URL and your internet connection.")
            return None
        feeds[podcast_name] = rss_url
        with open(feeds_path, "w") as f:
            json.dump(feeds, f, indent=2)
        print(f"Saved '{podcast_name}' for future use.")

    return feed, podcast_name

# ============================================================
# HISTORY
# Tracks all previously processed episodes in history.json.
# Used to detect and warn about duplicate episode processing.
# Each entry stores: title, season, episode number, date/time.
# ============================================================

def load_history():
    # Returns the full history list or empty list if none exists
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    return []

def save_history(entry):
    # Appends a new entry to history.json
    history = load_history()
    history.append(entry)
    with open(HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)

def check_duplicate(season, episode, config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Full Auto: always returns True (skip) if duplicate found
    #   - Guided Auto: uses the pre-configured proceed_on_duplicate
    #     flag set during upfront configuration — no prompt
    # When called interactively (config=None):
    #   - Original behaviour — prompts user to proceed or abort
    # ============================================================
    history = load_history()
    duplicates = [
        e for e in history
        if e.get("season") == season and e.get("episode") == episode
    ]

    if not duplicates:
        return False

    # Format duplicate info for display or logging
    duplicate_info = ", ".join(
        f"{e.get('title')} (processed {e.get('date')})"
        for e in duplicates
    )

    if config is not None:
        # ---- Pipeline mode — no prompting ----
        if config.get("skip_duplicates", True):
            # Default pipeline behaviour: skip duplicates silently
            print(f"⚠️  Duplicate detected: {duplicate_info}")
            print("   Skipping — duplicate processing disabled in pipeline mode.")
            return True
        else:
            # Guided Auto pre-approved proceeding with duplicate
            print(f"⚠️  Duplicate detected: {duplicate_info}")
            print("   Proceeding as configured.")
            return False

    # ---- Interactive mode — prompt user ----
    print(f"\n⚠️  Episode S{season}E{episode} has already been processed:")
    for e in duplicates:
        print(f"   - {e.get('title')} — processed on {e.get('date')}")

    choice = input("\n   Process it again anyway? (y/n): ").strip().lower()
    return choice != "y"

# ============================================================
# LATEST PROCESSED EPISODE
# Reads history.json and returns the most recently processed
# episode entry based on the logged date string.
# Used by check_new_episodes() to determine what's "new"
# relative to the last time the agent processed something.
# Returns None if history is empty or doesn't exist.
# ============================================================

def get_latest_processed():
    history = load_history()

    if not history:
        # No history yet — every episode would be considered new
        return None

    # Sort by date string descending and return the most recent entry
    # Date format is "%Y-%m-%d %H:%M" — sorts correctly as a string
    try:
        latest = sorted(history, key=lambda e: e.get("date", ""), reverse=True)[0]
        return latest
    except Exception:
        return None

# ============================================================
# NEW EPISODE CHECKER
# Silently fetches a saved RSS feed and compares its entries
# against history.json to find episodes that haven't been
# processed yet.
#
# Uses the first saved feed in feeds.json by default —
# designed to be called automatically on launch without
# requiring user interaction.
#
# Each returned entry contains:
#   - title   : Episode title
#   - season  : Season number (int)
#   - episode : Episode number (int)
#   - link    : Spotify/episode URL if available
#
# Returns an empty list if:
#   - No feeds are saved yet
#   - Feed cannot be reached
#   - All episodes are already in history
# ============================================================

def check_new_episodes():
    feeds_path = "feeds.json"

    # Abort silently if no feeds have been saved yet
    if not os.path.exists(feeds_path):
        return []

    try:
        with open(feeds_path, "r") as f:
            feeds = json.load(f)
    except Exception:
        # Don't interrupt launch if feeds.json is unreadable
        return []

    if not feeds:
        return []

    # Use the first saved feed for automatic detection
    # Future versions could check all saved feeds
    podcast_name, rss_url = list(feeds.items())[0]

    try:
        feed = feedparser.parse(rss_url)
    except Exception:
        # Don't interrupt launch if feed is unreachable
        return []

    # Load history to compare against
    history = load_history()

    # Build a set of already-processed (season, episode) tuples
    # for fast lookup during comparison
    processed = {
        (e.get("season"), e.get("episode"))
        for e in history
    }

    new_episodes = []

    for entry in feed.entries:
        try:
            entry_season  = int(entry.get("itunes_season", 0))
            entry_episode = int(entry.get("itunes_episode", 0))
        except (ValueError, TypeError):
            # Skip entries with malformed season/episode fields
            continue

        if (entry_season, entry_episode) not in processed:
            new_episodes.append({
                "title":   entry.get("title", "Unknown Title"),
                "season":  entry_season,
                "episode": entry_episode,
                "link":    entry.get("link", None),
                "podcast": podcast_name,
            })

    # Return newest first — RSS feeds are typically newest-first
    # so this preserves the natural feed order
    return new_episodes

# ============================================================
# SUBFOLDER CREATOR
# Creates a per-episode output folder structure under output/.
# Folder name format: {safe_title} - S{season}E{episode}
# Subfolders created: transcripts/, captions/, images/
# Returns a dict of paths used by all downstream scripts.
# ============================================================

def create_episode_folder(safe_title, season, episode):
    folder_name = f"{safe_title} - S{season}E{episode}"
    paths = {
        "root":        os.path.join("output", folder_name),
        "transcripts": os.path.join("output", folder_name, "transcripts"),
        "captions":    os.path.join("output", folder_name, "captions"),
        "images":      os.path.join("output", folder_name, "images"),
    }
    # exist_ok=True prevents errors if folders already exist
    for path in paths.values():
        os.makedirs(path, exist_ok=True)
    print(f"Episode folder created: output/{folder_name}")
    return paths

# ============================================================
# FETCH
# Main entry point called by main.py.
# Orchestrates the full fetch flow:
#   1. Load RSS feed from saved list or prompt for new one
#   2. Check for duplicate episode in history
#   3. Prompt for what to fetch (audio, cover art, link, all)
#   4. Search RSS feed entries for matching season + episode
#   5. Create per-episode output subfolder
#   6. Download requested assets
#   7. Save metadata.json for downstream scripts
#   8. Log episode to history.json
# ============================================================

def fetch_episode(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Season, episode and fetch choice pulled from config
    #   - No prompts at any decision point
    #   - Returns metadata dict on success, None on failure
    # When called interactively (config=None):
    #   - Original behaviour — prompts for all decisions
    # ============================================================
    result = load_feed(config)
    if not result:
        return None
    feed, podcast_name = result

    # ---- Season + episode selection ----
    if config is not None:
        season  = config.get("season")
        episode = config.get("episode")
        if not season or not episode:
            print("⚠️  Season and episode must be specified in pipeline config.")
            return None
    else:
        season  = int(input("\nEnter season number: ").strip())
        episode = int(input("Enter episode number: ").strip())

    # ---- Duplicate check ----
    # Passes config so behaviour is mode-appropriate
    if check_duplicate(season, episode, config):
        print("Fetch cancelled.")
        return None

    # ---- Fetch choice ----
    if config is not None:
        # Pipeline default: fetch everything
        choice = config.get("fetch_choice", "4")
    else:
        print("\nWhat would you like to fetch?")
        print("1. Audio only")
        print("2. Cover art only")
        print("3. Spotify link only")
        print("4. All")
        choice = input("Enter 1, 2, 3 or 4: ").strip()

    start = time.time()
    print("\nSearching for episode...")

    # Search feed entries for matching season + episode number
    match = None
    for entry in feed.entries:
        entry_season  = int(entry.get("itunes_season", 0))
        entry_episode = int(entry.get("itunes_episode", 0))
        if entry_season == season and entry_episode == episode:
            match = entry
            break

    if not match:
        print(f"⚠️  Episode S{season}E{episode} not found in feed. Check the season and episode numbers.")
        return None

    title      = match.title
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
    print(f"\nFound: {title}")

    # Create per-episode subfolder and store paths for downstream use
    episode_paths = create_episode_folder(safe_title, season, episode)

    # ---- Spotify Link ----
    spotify_link = None
    if choice in ("3", "4"):
        spotify_link = match.get("link", "No link found")
        print(f"Spotify link: {spotify_link}")

    # ---- Audio Download ----
    if choice in ("1", "4"):
        audio_url = None
        for link in match.links:
            if link.get("type", "").startswith("audio"):
                audio_url = link["href"]
                break

        if audio_url:
            try:
                print("\nDownloading audio...")
                audio_path = os.path.join(INPUT_FOLDER, f"{safe_title} - S{season}E{episode}.mp3")
                audio_data = requests.get(audio_url, stream=True)
                with open(audio_path, "wb") as f:
                    for chunk in audio_data.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Audio saved to: {audio_path}")
            except requests.exceptions.ConnectionError:
                print("⚠️  Could not download audio. Check your internet connection.")
            except Exception as e:
                print(f"⚠️  Audio download failed: {e}")
        else:
            print("⚠️  No audio URL found in feed for this episode.")

    # ---- Cover Art Download ----
    if choice in ("2", "4"):
        cover_url = (
            match.get("itunes_image", {}).get("href") or
            match.get("image", {}).get("href") or
            match.get("itunes_imageurl") or
            None
        )

        if cover_url:
            try:
                print("\nDownloading episode cover art...")
                cover_path = os.path.join(
                    episode_paths["images"],
                    f"{safe_title} - S{season}E{episode}_cover.jpg"
                )
                cover_data = requests.get(cover_url)
                with open(cover_path, "wb") as f:
                    f.write(cover_data.content)
                print(f"Cover art saved to: {cover_path}")
            except requests.exceptions.ConnectionError:
                print("⚠️  Could not download cover art. Check your internet connection.")
            except Exception as e:
                print(f"⚠️  Cover art download failed: {e}")
        else:
            print("\n⚠️  No episode-specific cover art found in feed.")

    elapsed = round(time.time() - start, 2)
    print(f"\nDone in {format_time(elapsed)}")

    # ---- Save Metadata ----
    metadata = {
        "title":         title,
        "safe_title":    safe_title,
        "season":        season,
        "episode":       episode,
        "spotify_link":  spotify_link,
        "episode_paths": episode_paths,
        "podcast_name":  podcast_name
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # ---- Update History ----
    from datetime import datetime
    save_history({
        "title":   title,
        "season":  season,
        "episode": episode,
        "date":    datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    return metadata