# ============================================================
# Podcast Agent — Image Generator
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Generates square (1080x1080) quote card images from
# approved captions, using the episode cover art as the
# background.
#
# Image style:
#   - Cover art blurred + dark overlay as background
#   - Quote text centred vertically with word wrap
#   - White text with subtle drop shadow for readability
#   - Font weight selected automatically based on background
#     brightness (SemiBold for dark, Medium for light)
#   - Links stripped from captions before rendering
#
# Pulls from:
#   - Twitter captions  (3 cards)
#   - Facebook captions (2 cards)
#
# All outputs saved to the per-episode images subfolder
# referenced from output/metadata.json.
# ============================================================

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import os
import sys
import time
import re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.utils import format_time, load_metadata

# ============================================================
# FONT PATHS
# Two weights used — selected dynamically based on background
# brightness. Both are Atkinson Hyperlegible Mono.
# Downloaded to assets/fonts/ by launch.py on first setup.
# ============================================================
FONT_MEDIUM  = "assets/fonts/AtkinsonHyperlegibleMono-Medium.ttf"
FONT_SEMIBOLD = "assets/fonts/AtkinsonHyperlegibleMono-SemiBold.ttf"

# ============================================================
# IMAGE SIZES
# Only square format is currently used.
# Add additional sizes here to generate multiple formats
# per caption in future (e.g. portrait for Stories).
# ============================================================
SIZES = {
    "square": (1080, 1080)
}

# ============================================================
# PLATFORM CAPTION COUNTS
# Defines how many captions to pull per platform.
# Must match platforms used in caption.py.
# ============================================================
PLATFORM_COUNTS = {
    "twitter":  3,
    "facebook": 2
}

# ============================================================
# COVER ART LOADER
# Scans the episode images subfolder for cover art files.
# If only one is found it's selected automatically.
# If multiple exist the user picks one or selects most recent.
# Returns: (cover_path, episode_name) or None on failure.
# ============================================================

def load_cover_art(images_folder, config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Uses most recently downloaded cover art automatically
    #   - Never prompts
    # When called interactively (config=None):
    #   - Original behaviour — lists files and prompts for choice
    # ============================================================
    if not os.path.exists(images_folder):
        print("⚠️  Images folder not found. Please run Fetch Episode first.")
        return None

    # Only look for files ending in _cover.jpg or _cover.png
    files = [f for f in os.listdir(images_folder) if f.endswith(("_cover.jpg", "_cover.png"))]

    if not files:
        print("⚠️  No cover art found. Please fetch an episode with cover art first.")
        return None

    # ---- Pipeline mode ----
    if config is not None:
        # Always use most recently downloaded cover art
        chosen = max(files, key=lambda f: os.path.getmtime(os.path.join(images_folder, f)))
        print(f"Using cover art: {chosen}")
        return os.path.join(images_folder, chosen), os.path.splitext(chosen)[0].replace("_cover", "")

    # ---- Interactive mode — original behaviour ----
    # Auto-select if only one cover art file exists
    if len(files) == 1:
        chosen = files[0]
    else:
        print("\nMultiple cover art files found:")
        for i, f in enumerate(files):
            print(f"  {i + 1}. {f}")
        print("  0. Use most recent")
        choice = input("Enter number: ").strip()
        if choice == "0":
            chosen = max(files, key=lambda f: os.path.getmtime(os.path.join(images_folder, f)))
        else:
            chosen = files[int(choice) - 1]

    print(f"Using cover art: {chosen}")
    # Strip _cover suffix from filename to get clean episode name
    return os.path.join(images_folder, chosen), os.path.splitext(chosen)[0].replace("_cover", "")

# ============================================================
# CAPTIONS LOADER
# Reads approved caption files from the episode captions
# subfolder. Strips numbering and URLs before returning,
# since images should contain only the quote text.
# Returns a list of cleaned caption strings up to `count`.
# ============================================================

def load_captions(captions_folder, platform, count, config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Prefers _pending_review caption files written by
    #     pipeline mode in caption.py
    #   - Falls back to approved caption files if no pending
    #     review files found
    #   - Uses most recent file automatically — never prompts
    # When called interactively (config=None):
    #   - Original behaviour — lists files and prompts for choice
    # ============================================================
    if not os.path.exists(captions_folder):
        print(f"⚠️  Captions folder not found. Please run Create Captions first.")
        return []

    # ---- Pipeline mode ----
    if config is not None:
        # Look for pending review files first — these are the ones
        # written by pipeline mode in caption.py
        pending_files = [
            f for f in os.listdir(captions_folder)
            if f.endswith(f"_{platform}_captions_pending_review.txt")
        ]
        approved_files = [
            f for f in os.listdir(captions_folder)
            if f.endswith(f"_{platform}_captions.txt")
        ]

        # Prefer pending review, fall back to approved
        files = pending_files or approved_files

        if not files:
            print(f"⚠️  No {platform} captions found. Please run Create Captions first.")
            return []

        # Always use most recent in pipeline mode
        chosen = max(files, key=lambda f: os.path.getmtime(os.path.join(captions_folder, f)))
        print(f"Using captions: {chosen}")

    else:
        # ---- Interactive mode — original behaviour ----
        # Match caption files for the specific platform
        files = [f for f in os.listdir(captions_folder) if f.endswith(f"_{platform}_captions.txt")]

        if not files:
            print(f"⚠️  No {platform} captions found. Please run Create Captions first.")
            return []

        # Auto-select if only one file exists
        if len(files) == 1:
            chosen = files[0]
        else:
            print(f"\nMultiple {platform} caption files found:")
            for i, f in enumerate(files):
                print(f"  {i + 1}. {f}")
            print("  0. Use most recent")
            choice = input("Enter number: ").strip()
            if choice == "0":
                chosen = max(files, key=lambda f: os.path.getmtime(os.path.join(captions_folder, f)))
            else:
                chosen = files[int(choice) - 1]

    path = os.path.join(captions_folder, chosen)
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split on numbered lines (e.g. "1.", "2.") to separate captions
    captions = re.split(r'\n(?=\d+\.)', raw.strip())
    cleaned = []
    for c in captions:
        c = re.sub(r'^\d+\.\s*', '', c).strip()  # Remove leading number
        c = re.sub(r'http\S+', '', c).strip()     # Remove URLs
        cleaned.append(c)

    # Return only the requested number of captions
    return cleaned[:count]

# ============================================================
# FONT SELECTOR
# Converts cover art to greyscale and calculates the average
# pixel brightness (0 = black, 255 = white).
# Dark backgrounds (avg < 100) get SemiBold for visibility.
# Light backgrounds get Medium since overlay handles contrast.
# Falls back to Medium if brightness analysis fails.
# ============================================================

def get_font_for_background(cover_path):
    try:
        img = Image.open(cover_path).convert("L")
        # Average all pixel values to get overall brightness
        avg_brightness = sum(img.getdata()) / (img.width * img.height)
        if avg_brightness < 100:
            print("  Dark background detected → using SemiBold")
            return FONT_SEMIBOLD
        else:
            print("  Light background detected → using Medium")
            return FONT_MEDIUM
    except Exception as e:
        print(f"⚠️  Could not analyse cover art brightness: {e}. Defaulting to Medium.")
        return FONT_MEDIUM

# ============================================================
# QUOTE CARD GENERATOR
# Builds a single quote card image from cover art + text.
#
# Process:
#   1. Open and resize cover art to target dimensions
#   2. Apply Gaussian blur (radius 6) to soften background
#   3. Paste semi-transparent dark overlay for text contrast
#   4. Select font weight based on background brightness
#   5. Word-wrap the quote text to fit within margins
#   6. Calculate vertical centre position for text block
#   7. Render each line with drop shadow then white text
#   8. Save as high-quality JPEG (95)
#
# Returns True on success, False on any failure.
# ============================================================

def make_quote_card(cover_path, quote_text, size, output_path, overlay_opacity=160):
    # overlay_opacity controls the darkness of the background overlay.
    # Default 160 (~63% opacity) — balances art visibility with readability.
    # Can be adjusted during image review:
    #   120 = lighter (more cover art visible)
    #   200 = darker  (stronger text contrast)
    W, H = size

    # ---- Background ----
    try:
        bg = Image.open(cover_path).convert("RGB")
        bg = bg.resize((W, H), Image.LANCZOS)
        # Blur softens the cover art so text remains the focus
        bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
    except FileNotFoundError:
        print(f"⚠️  Cover art file not found at: {cover_path}")
        return False
    except Exception as e:
        print(f"⚠️  Could not open cover art: {e}")
        return False

    try:
        # ---- Dark overlay ----
        # Opacity passed in as parameter — default 160, adjustable
        # during review for images where text contrast is poor
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, overlay_opacity))
        bg = bg.convert("RGBA")
        bg.paste(overlay, (0, 0), overlay)

        draw = ImageDraw.Draw(bg)

        # ---- Font ----
        font_path = get_font_for_background(cover_path)
        try:
            font = ImageFont.truetype(font_path, 34)
        except FileNotFoundError:
            print(f"⚠️  Font file not found at: {font_path}")
            print("   Run 'python launch.py --setup' to re-download fonts.")
            return False

        # ---- Word wrap ----
        # Builds lines by testing each word addition against max_width
        # Starts a new line when adding a word would exceed the margin
        margin = 100
        max_width = W - (margin * 2)
        words = quote_text.split()
        lines = []
        current = ""

        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        # ---- Vertical centring ----
        # Calculates total text block height and starts from
        # the point that centres the block within the image
        line_height = 34 + 16   # Font size + line spacing
        total_height = len(lines) * line_height
        y = (H - total_height) // 2

        # ---- Text rendering ----
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            # Centre each line horizontally
            x = (W - (bbox[2] - bbox[0])) // 2
            # Draw shadow slightly offset for depth
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
            # Draw white text on top
            draw.text((x, y), line, font=font, fill="white")
            y += line_height

        bg = bg.convert("RGB")
        bg.save(output_path, quality=95)
        print(f"  Saved: {output_path}")
        return True

    except Exception as e:
        print(f"⚠️  Failed to generate quote card: {e}")
        return False
    
# ============================================================
# IMAGE REVIEW + REGENERATION
# Called after all quote cards are generated.
# Displays a numbered summary of all generated images with
# their platform, index and a short caption preview.
# Prompts the user per image to approve, regenerate with a
# lighter overlay for better readability, or skip (delete).
#
# Regeneration adjusts the overlay opacity from 160 to 120
# (lighter) to improve text contrast on problem images.
# A second regeneration attempt uses opacity 200 (darker)
# if the lighter version is also rejected.
#
# Prints a final confirmed output list on completion.
# ============================================================

def review_images(generated):
    """
    Reviews generated images one by one with approve/regenerate/skip options.

    Args:
        generated (list): Each entry is a dict with keys:
            - output_path  (str)  : Path to the saved image file
            - cover_path   (str)  : Path to cover art used
            - caption      (str)  : Caption text rendered on image
            - platform     (str)  : Platform name (twitter/facebook)
            - index        (int)  : Caption number within platform
            - size_name    (str)  : Size format label (e.g. "square")
            - size         (tuple): Image dimensions (W, H)

    Returns:
        list: Paths of all confirmed (approved) images.
    """

    if not generated:
        print("⚠️  No images to review.")
        return []

    print("\n" + "=" * 40)
    print("     🖼️  IMAGE REVIEW")
    print("=" * 40)

    # ---- Summary list ----
    # Show all generated images upfront so user knows what to expect
    print("\nGenerated images:")
    for i, item in enumerate(generated, 1):
        caption_preview = item["caption"][:60] + "..." if len(item["caption"]) > 60 else item["caption"]
        print(f"  {i}. [{item['platform'].upper()}] Quote {item['index']} — \"{caption_preview}\"")

    print(f"\nReviewing {len(generated)} image(s) one by one...\n")

    confirmed = []

    for i, item in enumerate(generated, 1):
        caption_preview = item["caption"][:60] + "..." if len(item["caption"]) > 60 else item["caption"]

        print("-" * 40)
        print(f"Image {i} of {len(generated)}")
        print(f"Platform : {item['platform'].upper()}")
        print(f"Caption  : \"{caption_preview}\"")
        print(f"Saved at : {item['output_path']}")
        print("-" * 40)
        print("  1. Approve")
        print("  2. Regenerate (lighter overlay)")
        print("  3. Skip (delete this image)")

        while True:
            decision = input("Enter choice: ").strip()

            if decision == "1":
                # User approved — add to confirmed list
                confirmed.append(item["output_path"])
                print(f"✅ Image {i} approved.")
                break

            elif decision == "2":
                # ---- Regenerate with adjusted overlay ----
                # First attempt uses lighter overlay (opacity 120)
                # to improve readability on darker cover art
                print(f"\nRegenerating with lighter overlay...")
                success = make_quote_card(
                    item["cover_path"],
                    item["caption"],
                    item["size"],
                    item["output_path"],
                    overlay_opacity=120
                )

                if success:
                    print(f"✅ Regenerated. Review the updated image.")
                    print("  1. Approve")
                    print("  2. Regenerate again (darker overlay)")
                    print("  3. Skip (delete this image)")

                    retry = input("Enter choice: ").strip()

                    if retry == "1":
                        confirmed.append(item["output_path"])
                        print(f"✅ Image {i} approved.")
                        break
                    elif retry == "2":
                        # Second attempt uses darker overlay (opacity 200)
                        print(f"\nRegenerating with darker overlay...")
                        success2 = make_quote_card(
                            item["cover_path"],
                            item["caption"],
                            item["size"],
                            item["output_path"],
                            overlay_opacity=200
                        )
                        if success2:
                            confirmed.append(item["output_path"])
                            print(f"✅ Image {i} approved with darker overlay.")
                        else:
                            print(f"⚠️  Regeneration failed. Skipping image {i}.")
                        break
                    else:
                        # User skipped after regeneration
                        if os.path.exists(item["output_path"]):
                            os.remove(item["output_path"])
                        print(f"🗑️  Image {i} deleted.")
                        break
                else:
                    print(f"⚠️  Regeneration failed. Keeping original.")
                    confirmed.append(item["output_path"])
                    break

            elif decision == "3":
                # Remove the file from disk on skip
                if os.path.exists(item["output_path"]):
                    os.remove(item["output_path"])
                print(f"🗑️  Image {i} deleted.")
                break

            else:
                print("⚠️  Invalid choice. Please enter 1, 2 or 3.")

    # ---- Final confirmed output list ----
    print("\n" + "=" * 40)
    print("     ✅  REVIEW COMPLETE")
    print("=" * 40)
    if confirmed:
        print(f"\n{len(confirmed)} image(s) confirmed:\n")
        for path in confirmed:
            print(f"  → {path}")
    else:
        print("\nNo images were approved.")

    return confirmed

# ============================================================
# MAIN
# Entry point called by main.py.
# Orchestrates the full image generation flow:
#   1. Load episode metadata and subfolder paths
#   2. Load episode cover art from images subfolder
#   3. For each platform, load the required number of captions
#   4. Generate a quote card per caption per size format
#   5. Track and report success/fail counts on completion
# ============================================================

def generate_images(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - All loaders use config to select files automatically
    #   - Post-generation review is skipped entirely
    #   - Returns list of generated image paths for pipeline summary
    # When called interactively (config=None):
    #   - Original behaviour — prompts where needed, offers review
    # ============================================================
    metadata = load_metadata()
    if not metadata:
        return None

    episode_paths = metadata.get("episode_paths")
    if not episode_paths:
        print("⚠️  Episode folder info missing. Please re-run Fetch Episode.")
        return None

    result = load_cover_art(episode_paths["images"], config)
    if not result:
        return None
    cover_path, episode_name = result

    start = time.time()
    success_count = 0
    fail_count    = 0

    # Collect all successfully generated images for post-generation review
    generated = []

    for platform, count in PLATFORM_COUNTS.items():
        captions = load_captions(episode_paths["captions"], platform, count, config)
        if not captions:
            continue

        print(f"\nGenerating {platform.upper()} quote cards...")
        for i, caption in enumerate(captions, 1):
            for size_name, size in SIZES.items():
                filename    = f"{episode_name}_{platform}_quote{i}_{size_name}.jpg"
                output_path = os.path.join(episode_paths["images"], filename)
                success     = make_quote_card(cover_path, caption, size, output_path)

                if success:
                    success_count += 1
                    # Store full context for each image so review_images()
                    # has everything it needs to regenerate if requested
                    generated.append({
                        "output_path": output_path,
                        "cover_path":  cover_path,
                        "caption":     caption,
                        "platform":    platform,
                        "index":       i,
                        "size_name":   size_name,
                        "size":        size,
                    })
                else:
                    fail_count += 1

    elapsed = round(time.time() - start, 2)
    print(f"\nAll images generated in {format_time(elapsed)}")
    print(f"✅ {success_count} saved  |  ⚠️  {fail_count} failed")

    if config is not None:
        # ---- Pipeline mode — skip review entirely ----
        # Return paths for pipeline summary
        print("\nImage review skipped in pipeline mode.")
        return [item["output_path"] for item in generated]

    # ---- Interactive mode — offer post-generation review ----
    if generated:
        print("\nWould you like to review the generated images?")
        print("  1. Yes — review now")
        print("  2. No  — keep all and continue")
        review_choice = input("Enter 1 or 2: ").strip()

        if review_choice == "1":
            review_images(generated)

    return [item["output_path"] for item in generated] if generated else None