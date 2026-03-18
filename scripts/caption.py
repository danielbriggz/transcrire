# ============================================================
# Podcast Agent — Caption Generator
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Generates platform-specific social media captions from a
# podcast transcript using the Google Gemini API.
#
# Supports three platforms:
#   - Twitter  (short, punchy, under 250 characters)
#   - LinkedIn (professional, reflective)
#   - Facebook (warm, conversational)
#
# Features:
#   - Detects and prefers timestamped transcripts
#   - Preview + approve/regenerate before saving
#   - Generates timestamp reference lists when applicable
#   - All outputs saved to per-episode subfolder
# ============================================================

import json
from google import genai
import os
import sys
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import GEMINI_API_KEY
from scripts.utils import format_time, load_metadata

# ============================================================
# PLATFORM REGISTRY
# Defines formatting instructions per platform.
# Each entry contains an instruction template with a {link}
# placeholder that is filled at prompt build time.
# Add new platforms here to extend caption generation.
# ============================================================

PLATFORMS = {
    "twitter": {
        "instruction": """Format each one as a short tweet (under 250 characters) followed by this link: {link}
        Number them 1 to 5.
        Only return the 5 tweets, nothing else.""",
    },
    "linkedin": {
        "instruction": """Format each one as a professional post (3-4 sentences with context). End each with a reflective question and this link: {link}
        Number them 1 to 5.
        Only return the 5 posts, nothing else.""",
    },
    "facebook": {
        "instruction": """Format each one as a warm, conversational post that encourages listeners to share their thoughts. End each with this link: {link}
        Number them 1 to 5.
        Only return the 5 posts, nothing else.""",
    }
}

# ============================================================
# TRANSCRIPT LOADER
# Reads from the episode's transcripts subfolder.
# Detects and prefers timestamped transcripts (_segments or
# _words) over plain text transcripts.
# Timestamped files are labelled with ⏱️ in the menu.
# Returns: (transcript text, episode name, is_timestamped)
# ============================================================

def load_transcript(transcript_folder, config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Uses config["transcript_type"] to select the correct
    #     transcript file directly without prompting
    #   - Falls back to most recent timestamped transcript if
    #     no type specified
    #   - Never prompts
    # When called interactively (config=None):
    #   - Original behaviour — lists files and prompts for choice
    # ============================================================
    if not os.path.exists(transcript_folder):
        print("⚠️  Transcript folder not found. Please run Transcribe first.")
        return None, None, False

    files = [f for f in os.listdir(transcript_folder) if f.endswith('.txt')]

    if not files:
        print("⚠️  No transcript found. Please run Transcribe first.")
        return None, None, False

    # Sort files into timestamped and plain categories
    segments_files = [f for f in files if f.endswith("_segments.txt")]
    words_files    = [f for f in files if f.endswith("_words.txt")]
    plain_files    = [f for f in files if not f.endswith(("_segments.txt", "_words.txt"))]

    # ---- Pipeline mode ----
    if config is not None:
        transcript_type = config.get("transcript_type", "segments")

        if transcript_type == "segments" and segments_files:
            # Use most recent segments transcript
            chosen = max(segments_files, key=lambda f: os.path.getmtime(
                os.path.join(transcript_folder, f)))
        elif transcript_type == "words" and words_files:
            # Use most recent words transcript
            chosen = max(words_files, key=lambda f: os.path.getmtime(
                os.path.join(transcript_folder, f)))
        elif plain_files:
            # Fall back to plain if typed transcript not found
            chosen = max(plain_files, key=lambda f: os.path.getmtime(
                os.path.join(transcript_folder, f)))
        else:
            # Last resort — use any available transcript
            chosen = max(files, key=lambda f: os.path.getmtime(
                os.path.join(transcript_folder, f)))

        print(f"Using transcript: {chosen}")
        is_timestamped = chosen.endswith(("_segments.txt", "_words.txt"))
        path = os.path.join(transcript_folder, chosen)
        with open(path, "r", encoding="utf-8") as f:
            return f.read(), os.path.splitext(chosen)[0].replace("_segments", "").replace("_words", ""), is_timestamped

    # ---- Interactive mode — original behaviour ----
    timestamped = len(segments_files) > 0 or len(words_files) > 0

    if timestamped:
        # Surface timestamped files at the top of the selection list
        preferred = segments_files or words_files
        print("\n✅ Timestamped transcript detected — reference list will be generated.")
    else:
        preferred = plain_files

    # Merge: preferred files first, then the rest
    all_files = preferred + [f for f in files if f not in preferred]

    print("\nAvailable transcripts:")
    for i, f in enumerate(all_files):
        # Mark timestamped files visually in the menu
        label = " ⏱️" if f.endswith(("_segments.txt", "_words.txt")) else ""
        print(f"  {i + 1}. {f}{label}")
    print("  0. Use most recent")
    choice = input("Enter number: ").strip()

    if choice == "0":
        chosen = max(all_files, key=lambda f: os.path.getmtime(os.path.join(transcript_folder, f)))
        print(f"Using: {chosen}")
    elif choice.isdigit() and 1 <= int(choice) <= len(all_files):
        chosen = all_files[int(choice) - 1]
    else:
        print("⚠️  Invalid choice.")
        return None, None, False

    is_timestamped = chosen.endswith(("_segments.txt", "_words.txt"))
    path = os.path.join(transcript_folder, chosen)
    with open(path, "r", encoding="utf-8") as f:
        # Strip type suffix from episode name for clean output filenames
        return f.read(), os.path.splitext(chosen)[0].replace("_segments", "").replace("_words", ""), is_timestamped

# ============================================================
# SPOTIFY LINK
# Pulls the episode link from metadata.json.
# Falls back to manual input if not present — this can happen
# if fetch.py was run with option 1 (audio only) or 2 (cover
# art only), which skips the Spotify link fetch.
# ============================================================

def load_spotify_link(metadata, config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Always uses the link from metadata.json
    #   - If no link found, logs a warning and returns None
    #     rather than prompting — pipeline continues without link
    # When called interactively (config=None):
    #   - Original behaviour — falls back to manual input
    # ============================================================
    link = metadata.get("spotify_link")

    if link:
        print(f"Using Spotify link: {link}")
        return link

    if config is not None:
        # Pipeline mode — no prompting, warn and continue without link
        print("⚠️  No Spotify link found in metadata.")
        print("   Captions will be generated without an episode link.")
        return ""

    # Interactive mode — fall back to manual input
    return input("\nNo Spotify link in metadata. Paste it manually: ").strip()

# ============================================================
# PROMPT BUILDER
# Constructs the Gemini prompt for caption generation.
# Injects the platform-specific instruction and episode link.
# Timestamps are intentionally excluded from captions —
# they appear only in the reference list (see below).
# ============================================================

def build_prompt(instruction, transcript, link):
    return f"""
    You are a social media assistant for a podcast.
    Read this transcript and pick 5 of the most interesting, thought-provoking, or quotable moments. Draw from across the episode. Prioritise moments that challenge assumptions or reframe familiar ideas.
    The tone is casual/conversational with a gentle + philosophical approach.
    Do not hallucinate. Do not make up anything outside the transcript.
    {instruction.format(link=link)}

    Transcript:
    {transcript}
    """

def build_reference_prompt(transcript, captions_text, platform):
    # Constructs a separate prompt asking Gemini to map each
    # caption back to its source timestamp in the transcript.
    # Only called when a timestamped transcript was used.
    return f"""
    You are a research assistant for a podcast editor.
    Below is a timestamped transcript and a set of {platform} captions generated from it.
    For each caption, identify the exact transcript segment it was drawn from.

    Return a plain text reference list in this format:
    Caption 1: [00:00:00 - 00:00:00] "exact or near-exact quote from transcript"
    Caption 2: [00:00:00 - 00:00:00] "exact or near-exact quote from transcript"
    ...and so on.

    Only return the reference list, nothing else.

    Transcript:
    {transcript}

    Captions:
    {captions_text}
    """

# ============================================================
# GEMINI API CALL
# Wraps all Gemini generate_content calls in one place.
# Handles specific error codes with actionable messages:
#   401 — invalid API key
#   429 — rate limit exceeded
#   404 — model not found (name may have changed)
# Returns response text or None on failure.
# ============================================================

def call_gemini(client, prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        if "401" in str(e) or "invalid" in str(e).lower():
            print("⚠️  Invalid Gemini API key. Run 'python launch.py --setup' to update it.")
        elif "429" in str(e):
            print("⚠️  Gemini rate limit reached. Wait a moment and try again.")
        elif "404" in str(e):
            print("⚠️  Gemini model not found. The model name may have changed.")
        else:
            print(f"⚠️  Gemini API error: {e}")
            print("   Check your internet connection or API key.")
        return None
    
# ============================================================
# SINGLE CAPTION REGENERATOR
# Called when the user selects option 4 in the preview menu.
# Displays all captions numbered and prompts the user to
# select one to replace. Builds a targeted Gemini prompt
# that regenerates only that caption in the same style and
# format as the rest, then splices it back into the full
# captions text before returning to the preview loop.
# ============================================================

def regenerate_single_caption(captions_text, platform, client, spotify_link):
    # ---- Parse individual captions from the full text ----
    # Split on numbered lines to isolate each caption
    lines = captions_text.strip().split("\n")
    captions = []
    current = []

    for line in lines:
        if re.match(r'^\d+\.', line.strip()) and current:
            # New numbered caption starts — save the previous one
            captions.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        captions.append("\n".join(current).strip())

    if not captions:
        print("⚠️  Could not parse individual captions. Try regenerating all instead.")
        return captions_text

    # ---- Display numbered caption list for selection ----
    print(f"\nWhich caption would you like to regenerate?")
    for i, caption in enumerate(captions, 1):
        # Show a short preview of each caption for quick identification
        preview = caption[:80] + "..." if len(caption) > 80 else caption
        print(f"\n  {i}. {preview}")
    print("\n  0. Cancel")

    choice = input("\nEnter caption number: ").strip()

    if choice == "0" or not choice.isdigit():
        print("Cancelled.")
        return captions_text

    index = int(choice) - 1
    if index < 0 or index >= len(captions):
        print("⚠️  Invalid selection.")
        return captions_text

    original = captions[index]
    print(f"\nRegenerating caption {int(choice)}...")

    # ---- Build targeted single-caption regeneration prompt ----
    # Provides full context so the replacement matches the style
    # and format of the other captions in the set
    prompt = f"""
    You are a social media assistant for a podcast.
    Below is a set of {platform} captions. One of them needs to be replaced.

    Here are all the current captions for context:
    {captions_text}

    The caption to replace is:
    {original}

    Write ONE new {platform} caption in exactly the same style, tone and format
    as the others. It must cover a different moment from the transcript than
    the one it is replacing. End it with the same episode link used in the others.

    Return only the new caption text, nothing else. Do not number it.
    """

    new_caption = call_gemini(client, prompt)

    if not new_caption:
        print("⚠️  Regeneration failed. Keeping original caption.")
        return captions_text

    # ---- Splice replacement back into full captions text ----
    # Replaces only the selected caption, preserving all others
    captions[index] = f"{index + 1}. {new_caption.strip()}"

    # Renumber all captions cleanly after replacement
    rebuilt = []
    for i, caption in enumerate(captions, 1):
        # Strip any existing number prefix before renumbering
        clean = re.sub(r'^\d+\.\s*', '', caption).strip()
        rebuilt.append(f"{i}. {clean}")

    updated_text = "\n\n".join(rebuilt)
    print(f"✅ Caption {int(choice)} replaced.")
    return updated_text

# ============================================================
# CAPTION PREVIEW + APPROVAL
# Displays generated captions before saving and prompts
# the user to approve, regenerate all, edit one, or skip.
#
# Options:
#   1. Approve and save — writes captions to file
#   2. Regenerate all  — re-calls Gemini with same prompt
#   3. Skip platform   — discards captions, moves on
#   4. Edit individual — select one caption to regenerate
#
# Loops until a valid terminal decision (approve or skip)
# is made. Files are only written after explicit approval.
# ============================================================

def preview_and_approve(captions_text, platform, client, prompt, spotify_link):
    while True:
        print(f"\n--- {platform.upper()} CAPTIONS PREVIEW ---\n")
        print(captions_text)
        print("\n" + "-" * 40)
        print("  1. Approve and save")
        print("  2. Regenerate all")
        print("  3. Skip this platform")
        print("  4. Edit an individual caption")
        decision = input("Enter choice: ").strip()

        if decision == "1":
            # User approved — return captions for saving
            return captions_text

        elif decision == "2":
            # Regenerate entire set with same prompt
            print(f"\nRegenerating {platform.upper()} captions...")
            new_captions = call_gemini(client, prompt)
            if new_captions:
                # Update and loop back to preview with new captions
                captions_text = new_captions
            else:
                print("⚠️  Regeneration failed. Keeping previous result.")

        elif decision == "3":
            # User skipped — return None to signal no file should be saved
            print(f"Skipping {platform.upper()}.")
            return None

        elif decision == "4":
            # Delegate to single-caption regenerator
            # Returns updated captions_text with one caption replaced
            captions_text = regenerate_single_caption(
                captions_text, platform, client, spotify_link
            )
            # Loop back to preview with updated captions

        else:
            print("⚠️  Invalid choice. Please enter 1, 2, 3 or 4.")

# ============================================================
# REFERENCE LIST GENERATOR
# Only called when a timestamped transcript was used.
# Makes a separate Gemini call to map each caption back to
# its source timestamp in the transcript.
# Saved as a separate _references.txt file per platform —
# useful for locating exact audio segments for clip editing.
# ============================================================

def generate_reference_list(client, transcript, captions_text, platform, captions_folder, episode_name):
    print(f"\nGenerating reference list for {platform.upper()}...")
    prompt = build_reference_prompt(transcript, captions_text, platform)
    references = call_gemini(client, prompt)

    if not references:
        print(f"⚠️  Could not generate reference list for {platform.upper()}.")
        return

    filename = f"{episode_name}_{platform}_references.txt"
    output_path = os.path.join(captions_folder, filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"CAPTION REFERENCES — {platform.upper()}\n")
        f.write("=" * 40 + "\n\n")
        f.write(references)

    print(f"✅ Reference list saved to: {output_path}")

# ============================================================
# MAIN
# Entry point called by main.py.
# Orchestrates the full caption generation flow:
#   1. Load episode metadata and subfolder paths
#   2. Load transcript (prefers timestamped)
#   3. Load Spotify episode link
#   4. Choose platform(s) to generate for
#   5. Generate captions via Gemini
#   6. Preview and approve/regenerate per platform
#   7. Save approved captions to episode subfolder
#   8. Generate reference list if transcript was timestamped
# ============================================================

def generate_captions(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Platform selection pulled from config["caption_platforms"]
    #     (list of platform names, or ["all"])
    #   - Captions auto-approved — saved with _pending_review
    #     suffix so user knows they haven't been manually checked
    #   - Reference list still generated if timestamped transcript
    #   - No preview or approval prompts
    # When called interactively (config=None):
    #   - Original behaviour — prompts for platform, shows preview
    # ============================================================
    metadata = load_metadata()
    if not metadata:
        return

    episode_paths = metadata.get("episode_paths")
    if not episode_paths:
        print("⚠️  Episode folder info missing. Please re-run Fetch Episode.")
        return

    transcript, episode_name, is_timestamped = load_transcript(
        episode_paths["transcripts"], config
    )
    if not transcript:
        return

    spotify_link = load_spotify_link(metadata, config)

    # ---- Platform selection ----
    if config is not None:
        # Pipeline mode — read platforms from config
        selected = config.get("caption_platforms", ["all"])
        if selected == ["all"] or "all" in selected:
            platforms_to_run = PLATFORMS
        else:
            # Filter to only the configured platforms
            platforms_to_run = {
                k: v for k, v in PLATFORMS.items()
                if k in selected
            }
        print(f"\nGenerating captions for: {', '.join(platforms_to_run.keys()).upper()}")
    else:
        print("\nWhich platform would you like to generate captions for?")
        for i, name in enumerate(PLATFORMS.keys()):
            print(f"  {i + 1}. {name.capitalize()}")
        print("  0. All platforms")
        choice = input("Enter choice: ").strip()

        if choice == "0":
            platforms_to_run = PLATFORMS
        elif choice.isdigit() and 1 <= int(choice) <= len(PLATFORMS):
            chosen = list(PLATFORMS.keys())[int(choice) - 1]
            platforms_to_run = {chosen: PLATFORMS[chosen]}
        else:
            print("⚠️  Invalid choice.")
            return

    print("\nGenerating captions...")
    start = time.time()

    # Initialise Gemini client — shared across all platform calls
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"⚠️  Could not initialise Gemini client: {e}")
        return

    # Track output paths for pipeline summary
    output_paths = []

    for name, settings in platforms_to_run.items():
        print(f"\nGenerating {name.upper()} captions...")
        prompt = build_prompt(settings["instruction"], transcript, spotify_link)

        captions_text = call_gemini(client, prompt)
        if not captions_text:
            print(f"⚠️  Skipping {name.upper()} due to generation error.")
            continue

        if config is not None:
            # ---- Pipeline mode — auto-approve with pending_review suffix ----
            # Suffix signals to the user that captions need manual review
            # before posting — never silently treated as final
            filename   = f"{episode_name}_{name}_captions_pending_review.txt"
            output_path = os.path.join(episode_paths["captions"], filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(captions_text)
            print(f"✅ {name.upper()} captions saved (pending review): {output_path}")
            output_paths.append(output_path)

        else:
            # ---- Interactive mode — show preview and approval flow ----
            # Pass spotify_link so single-caption regeneration can
            # maintain the correct episode link in replacement captions
            approved = preview_and_approve(captions_text, name, client, prompt, spotify_link)
            if not approved:
                continue

            # Save approved captions to episode subfolder
            filename    = f"{episode_name}_{name}_captions.txt"
            output_path = os.path.join(episode_paths["captions"], filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(approved)
            print(f"✅ {name.upper()} captions saved to: {output_path}")
            output_paths.append(output_path)

        # Generate timestamp reference list if applicable
        # Runs in both pipeline and interactive mode when timestamped
        if is_timestamped:
            generate_reference_list(
                client, transcript, captions_text if config else approved,
                name, episode_paths["captions"], episode_name
            )

    elapsed = round(time.time() - start, 2)
    print(f"\nAll done in {format_time(elapsed)}")

    # Return output paths for pipeline summary
    return output_paths if output_paths else None