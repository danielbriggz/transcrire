# ============================================================
# Podcast Agent — Main Menu
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Central hub for the Podcast Agent pipeline.
# Presents audio source selection first, then routes to the
# appropriate pipeline steps based on the chosen source.
#
# PC Upload: transcription only — save transcript anywhere
# Podcast RSS: full pipeline — fetch, transcribe, caption, images
#
# Always run via launch.py, not directly.
# ============================================================

import sys
import os
import json

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from scripts.fetch      import fetch_episode
from scripts.transcribe import transcribe
from scripts.caption    import generate_captions
from scripts.imagegen   import generate_images

METADATA_PATH = "output/metadata.json"

# ============================================================
# RSS PIPELINE MENU REGISTRY
# Only used when audio source is Podcast RSS.
# PC Upload path only uses transcribe.
# ============================================================
RSS_MENU = {
    "1": ("Fetch Episode",   fetch_episode),
    "2": ("Transcribe",      transcribe),
    "3": ("Create Captions", generate_captions),
    "4": ("Generate Images", generate_images),
}

NEXT = {
    "1": "2",
    "2": "3",
    "3": "4",
}

# ============================================================
# METADATA + STATUS
# ============================================================

def load_metadata():
    if not os.path.exists(METADATA_PATH):
        return None
    try:
        with open(METADATA_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None

def check_status(metadata):
    status = {
        "1": False,
        "2": False,
        "3": False,
        "4": False,
    }

    if not metadata:
        return status

    episode_paths = metadata.get("episode_paths", {})

    if episode_paths:
        status["1"] = True

    transcript_folder = episode_paths.get("transcripts", "")
    if os.path.exists(transcript_folder):
        txts = [f for f in os.listdir(transcript_folder) if f.endswith(".txt")]
        status["2"] = len(txts) > 0

    captions_folder = episode_paths.get("captions", "")
    if os.path.exists(captions_folder):
        caps = [f for f in os.listdir(captions_folder) if f.endswith("_captions.txt")]
        status["3"] = len(caps) > 0

    images_folder = episode_paths.get("images", "")
    if os.path.exists(images_folder):
        imgs = [
            f for f in os.listdir(images_folder)
            if f.endswith(".jpg") and "_quote" in f
        ]
        status["4"] = len(imgs) > 0

    return status

def get_status_icon(completed):
    return "✅" if completed else "⬜"

# ============================================================
# NEW EPISODE NOTIFICATIONS
# ============================================================

def load_new_episodes():
    new_episodes_path = "output/new_episodes.json"
    if not os.path.exists(new_episodes_path):
        return []
    try:
        with open(new_episodes_path, "r") as f:
            return json.load(f)
    except Exception:
        return []

def jump_to_fetch(episode):
    print(f"\n--- Fetch Episode ---")
    print(f"Loading: {episode['title']} (S{episode['season']}E{episode['episode']})")
    print(f"\nSeason:  {episode['season']}")
    print(f"Episode: {episode['episode']}")
    print(f"Title:   {episode['title']}")
    if episode.get("link"):
        print(f"Link:    {episode['link']}")
    print("\nProceeding to Fetch Episode...")

    new_episodes_path = "output/new_episodes.json"
    try:
        with open(new_episodes_path, "r") as f:
            new_episodes = json.load(f)
        updated = [
            e for e in new_episodes
            if not (e.get("season") == episode["season"] and
                    e.get("episode") == episode["episode"])
        ]
        if updated:
            with open(new_episodes_path, "w") as f:
                json.dump(updated, f, indent=2)
        else:
            os.remove(new_episodes_path)
    except Exception:
        pass

    run_rss_step("1")

# ============================================================
# PC UPLOAD PATH
# Transcription only — no fetch, captions or images.
# Prompts for save location after transcription completes.
# ============================================================

def run_pc_upload():
    print("\n" + "=" * 40)
    print("     💻  PC UPLOAD — TRANSCRIBE")
    print("=" * 40)
    print("\nThis will transcribe an audio file from your computer.")
    print("No captions or images will be generated.\n")

    # Run transcription — pick_audio() will prompt for custom path
    output_path = transcribe()

    if not output_path:
        print("⚠️  Transcription did not complete.")
        input("\nPress Enter to return to main menu...")
        return

    # ---- Prompt for save location ----
    print(f"\nTranscript saved to: {output_path}")
    print("\nWould you like to copy it to a different location?")
    print("  1. Yes — specify a folder")
    print("  2. No  — keep it where it is")
    save_choice = input("Enter 1 or 2: ").strip()

    if save_choice == "1":
        dest_folder = input("Paste destination folder path: ").strip().strip('"')
        if not os.path.exists(dest_folder):
            try:
                os.makedirs(dest_folder, exist_ok=True)
            except Exception as e:
                print(f"⚠️  Could not create folder: {e}")
                input("\nPress Enter to return to main menu...")
                return

        import shutil
        filename    = os.path.basename(output_path)
        dest_path   = os.path.join(dest_folder, filename)
        try:
            shutil.copy2(output_path, dest_path)
            print(f"✅ Transcript also saved to: {dest_path}")
        except Exception as e:
            print(f"⚠️  Could not copy transcript: {e}")

    input("\nPress Enter to return to main menu...")

# ============================================================
# RSS PIPELINE PATH
# Full pipeline — fetch, transcribe, captions, images.
# ============================================================

def print_rss_menu(metadata, status, new_episodes):
    print("\n" + "=" * 40)
    print("        🎙️  PODCAST AGENT — RSS")
    print("=" * 40)

    if metadata:
        podcast_name = metadata.get("podcast_name", "")
        title        = metadata.get("title", "")
        season       = metadata.get("season")
        episode      = metadata.get("episode")

        if title and season and episode:
            short_title = title[:28] + ('...' if len(title) > 28 else '')
            print(f"  📻 S{season}E{episode} — {short_title}")
        elif podcast_name:
            print(f"  🎙️  {podcast_name}")

        print("-" * 40)

    for key, (name, _) in RSS_MENU.items():
        icon = get_status_icon(status[key])
        print(f"  {key}. {icon} {name}")

    print("-" * 40)
    print("  0.    Back to source selection")
    print("=" * 40)

    if new_episodes:
        print(f"\n  🆕  {len(new_episodes)} new episode(s) available:")
        for i, ep in enumerate(new_episodes, 1):
            short_title = ep['title'][:35] + ('...' if len(ep['title']) > 35 else '')
            print(f"     {i}. S{ep['season']}E{ep['episode']} — {short_title}")
        print(f"\n  N.  Fetch a new episode from the list above")

def prompt_next(current_key):
    next_key = NEXT.get(current_key)

    if not next_key:
        input("\nPress Enter to return to menu...")
        return

    next_name = RSS_MENU[next_key][0]
    print(f"\nWhat would you like to do next?")
    print(f"  1. Continue to {next_name}")
    print(f"  2. Return to menu")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        run_rss_step(next_key)

def run_rss_step(key):
    name, func = RSS_MENU[key]
    print(f"\n--- {name} ---")
    try:
        func()
    except Exception as e:
        print(f"\n⚠️  Error in {name}: {e}")
    prompt_next(key)

def run_rss_pipeline():
    # ---- RSS pipeline loop ----
    previous_episode = None

    while True:
        metadata     = load_metadata()
        new_episodes = load_new_episodes()

        current_episode = (
            metadata.get("season"), metadata.get("episode")
        ) if metadata else None

        if current_episode != previous_episode:
            previous_episode = current_episode

        status = check_status(metadata)
        print_rss_menu(metadata, status, new_episodes)

        choice = input("Select an option: ").strip()

        if choice == "0":
            return  # Back to source selection

        elif choice.upper() == "N":
            if not new_episodes:
                print("\n⚠️  No new episodes detected.")
                continue
            if len(new_episodes) == 1:
                jump_to_fetch(new_episodes[0])
            else:
                print("\nWhich episode would you like to fetch?")
                for i, ep in enumerate(new_episodes, 1):
                    print(f"  {i}. S{ep['season']}E{ep['episode']} — {ep['title']}")
                print("  0. Cancel")
                ep_choice = input("Enter number: ").strip()
                if ep_choice == "0":
                    continue
                elif ep_choice.isdigit() and 1 <= int(ep_choice) <= len(new_episodes):
                    jump_to_fetch(new_episodes[int(ep_choice) - 1])
                else:
                    print("\n⚠️  Invalid choice.")

        elif choice in RSS_MENU:
            run_rss_step(choice)

        else:
            print("\nInvalid choice. Please try again.")

# ============================================================
# AUDIO SOURCE SELECTION
# Entry point — shown every time the main menu loads.
# Routes to PC upload path or RSS pipeline path.
# ============================================================

def print_source_menu():
    print("\n" + "=" * 40)
    print("        🎙️  PODCAST AGENT")
    print("=" * 40)
    print("  Select audio source:\n")
    print("  1. 💻  Upload from PC      (transcription only)")
    print("  2. 📡  Podcast RSS         (full pipeline)")
    print("-" * 40)
    print("  0.     Exit")
    print("=" * 40)

def main():
    while True:
        print_source_menu()
        choice = input("Select an option: ").strip()

        if choice == "0":
            print("\nGoodbye! 👋")
            sys.exit()

        elif choice == "1":
            # ---- PC Upload path ----
            run_pc_upload()

        elif choice == "2":
            # ---- RSS pipeline path ----
            run_rss_pipeline()

        else:
            print("\nInvalid choice. Please try again.")

main()