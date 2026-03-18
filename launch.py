# ============================================================
# Podcast Agent — Setup Checker & Launcher
# Developer: Daniel "Briggz" Adisa
# ============================================================
# This is the main entry point for the Podcast Agent.
# On first run it performs a full environment setup check
# before launching the main menu. On subsequent runs it
# skips checks and launches directly unless --setup is passed.
#
# Usage:
#   python launch.py           → launch (skip checks if done)
#   python launch.py --setup   → force re-run all checks
# ============================================================

import sys
import os
import subprocess

# ============================================================
# STEP 0: Setup Save
# Tracks whether first-time setup has been completed.
# Creates setup.json on success so checks are skipped
# on future runs unless --setup flag is used.
# ============================================================

SETUP_FLAG = "setup.json"

def is_setup_complete():
    # Returns True if setup.json exists — skips checks on launch
    return os.path.exists(SETUP_FLAG)

def mark_setup_complete():
    import json
    # Writes setup.json to signal that setup has been completed
    with open(SETUP_FLAG, "w") as f:
        json.dump({"setup_complete": True}, f)
    print("✅ Setup state saved.")

# ============================================================
# STEP 1: Python Version Check
# Warns if Python 3.13+ is detected — some audio libraries
# (e.g. pydub) are incompatible with 3.13+.
# Recommended version: Python 3.10–3.12.
# If user declines to proceed, opens the Python downloads
# page in their browser and exits.
# ============================================================

def check_python_version():
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    if version.major == 3 and version.minor >= 13:
        print("\n⚠️  Warning: You are running Python 3.13+.")
        print("   Some audio libraries may not work correctly.")
        print("   Recommended: Python 3.10–3.12")
        print("\n   Download the recommended version at:")
        print("   https://www.python.org/downloads/")
        choice = input("\n   Continue anyway with current version? (y/n): ").strip().lower()
        if choice != "y":
            # Only open browser if user chooses not to proceed
            print("\n   Opening Python downloads page...")
            print("   Instructions:")
            print("   1. Download Python 3.12 from the page that just opened")
            print("   2. During install, check 'Add Python to PATH'")
            print("   3. Create a new virtual environment with the correct version")
            print("   4. Re-run this script")
            import webbrowser
            webbrowser.open("https://www.python.org/downloads/")
            sys.exit()
    else:
        print("✅ Python version OK.")

# ============================================================
# STEP 2: Library Check + Install
# Maps Python module names to their pip package names.
# Attempts to import each module — if import fails,
# adds to missing list and offers a mass install.
# ============================================================

# module name → pip package name
REQUIRED_LIBRARIES = {
    "whisper":        "openai-whisper",
    "feedparser":     "feedparser",
    "requests":       "requests",
    "google.genai":   "google-genai",
    "groq":           "groq",
    "PIL":            "pillow",
    "plyer":          "plyer",
}

def check_libraries():
    missing = []

    # Try importing each required module
    for module, package in REQUIRED_LIBRARIES.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if not missing:
        print("✅ All libraries installed.")
        return

    print(f"\n⚠️  Missing libraries: {', '.join(missing)}")
    choice = input("   Install all now? (y/n): ").strip().lower()
    if choice == "y":
        print("\nInstalling...")
        # Uses the same Python executable as the current environment
        subprocess.run([sys.executable, "-m", "pip", "install"] + missing)
        print("✅ Libraries installed.")
    else:
        print("⚠️  Some features may not work without required libraries.")

# ============================================================
# STEP 3: ffmpeg Check
# ffmpeg is required for audio compression before Groq upload
# and for general audio processing by Whisper.
# Provides step-by-step Windows installation guidance
# if ffmpeg is not found on the system PATH.
# ============================================================

def check_ffmpeg():
    try:
        # Runs ffmpeg -version to confirm it's accessible on PATH
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        print("✅ ffmpeg found.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n⚠️  ffmpeg not found.")
        print("   ffmpeg is required for audio compression and transcription.")
        print("\n   To install:")
        print("   1. Go to https://ffmpeg.org/download.html")
        print("   2. Download the Windows essentials build from gyan.dev")
        print("   3. Extract and rename the folder to 'ffmpeg'")
        print("   4. Move it to C:\\ffmpeg")
        print("   5. Add C:\\ffmpeg\\bin to your system PATH")
        print("   6. Restart VS Code and run this script again")
        input("\n   Press Enter to continue without ffmpeg (some features will fail)...")

# ============================================================
# STEP 4: API Key Check
# Reads config.py line by line to extract key values.
# Prompts for any missing or placeholder keys.
# Validates each key with a live test call before saving
# to ensure only working keys are stored.
# ============================================================

CONFIG_PATH = "config.py"

def read_config():
    # Parses config.py into a key-value dict
    # Skips comment lines and blank lines
    config = {}
    if not os.path.exists(CONFIG_PATH):
        return config
    with open(CONFIG_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                config[key.strip()] = value.strip().strip('"').strip("'")
    return config

def write_api_key(key_name, value):
    # Updates an existing key in config.py or appends it if not found
    if not os.path.exists(CONFIG_PATH):
        open(CONFIG_PATH, "w").close()

    with open(CONFIG_PATH, "r") as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key_name):
            lines[i] = f'{key_name} = "{value}"\n'
            updated = True
            break

    if not updated:
        # Key not found in file — append it
        lines.append(f'{key_name} = "{value}"\n')

    with open(CONFIG_PATH, "w") as f:
        f.writelines(lines)

def validate_gemini_key(api_key):
    # Tests the Gemini key with a minimal generate call
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="say ok"
        )
        return True
    except Exception:
        return False

def validate_groq_key(api_key):
    # Tests the Groq key with a minimal chat completion call
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "say ok"}],
            max_tokens=5
        )
        return True
    except Exception:
        return False

# Maps each config key to its validator function
VALIDATORS = {
    "GEMINI_API_KEY": validate_gemini_key,
    "GROQ_API_KEY":   validate_groq_key,
}

def check_api_keys():
    config = read_config()
    key_info = {
        "GEMINI_API_KEY": "Google Gemini (https://aistudio.google.com/apikey)",
        "GROQ_API_KEY":   "Groq (https://console.groq.com)",
    }

    for key_name, description in key_info.items():
        value = config.get(key_name, "")

        # Detect placeholder values that haven't been replaced
        placeholder = "your-gemini-api-key-here" if "GEMINI" in key_name else "your-groq-api-key-here"

        if not value or value == placeholder:
            print(f"\n⚠️  {key_name} not set.")
            print(f"   Get your free key at: {description}")
            value = input(f"   Paste your {key_name}: ").strip()

        if value:
            print(f"   Validating {key_name}...")
            if VALIDATORS[key_name](value):
                # Only save to config.py once confirmed valid
                write_api_key(key_name, value)
                print(f"✅ {key_name} valid and saved.")
            else:
                print(f"❌ {key_name} is invalid.")
                retry = input("   Paste the correct key (or press Enter to skip): ").strip()
                if retry:
                    if VALIDATORS[key_name](retry):
                        write_api_key(key_name, retry)
                        print(f"✅ {key_name} valid and saved.")
                    else:
                        print(f"⚠️  Still invalid. Skipping — some features will not work.")
                else:
                    print(f"⚠️  Skipped. Some features will not work.")
        else:
            print(f"⚠️  {key_name} skipped. Some features will not work.")

# ============================================================
# STEP 5: Font Check
# Checks for the presence of Atkinson Hyperlegible Mono.
# Only checks for the Medium weight as a proxy for all weights
# since all weights are downloaded together.
# Downloads all 7 weights from Google Fonts if missing.
# ============================================================

FONTS_DIR = "assets/fonts"

# Only the Medium weight is checked — if it exists, all weights
# are assumed to be present since they're downloaded together
REQUIRED_FONT = "AtkinsonHyperlegibleMono-Medium.ttf"

# Direct .ttf URLs retrieved from Google Fonts CSS embed
FONT_URLS = {
    "AtkinsonHyperlegibleMono-ExtraLight": "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZnNeiDQ.ttf",
    "AtkinsonHyperlegibleMono-Light":      "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZQteiDQ.ttf",
    "AtkinsonHyperlegibleMono-Regular":    "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZHNeiDQ.ttf",
    "AtkinsonHyperlegibleMono-Medium":     "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZLteiDQ.ttf",
    "AtkinsonHyperlegibleMono-SemiBold":   "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZwtCiDQ.ttf",
    "AtkinsonHyperlegibleMono-Bold":       "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZ-9CiDQ.ttf",
    "AtkinsonHyperlegibleMono-ExtraBold":  "https://fonts.gstatic.com/s/atkinsonhyperlegiblemono/v8/tssNAoFBci4C4gvhPXrt3wjT1MqSzhA4t7IIcncBiyihrK15gZ4k_SaZnNCiDQ.ttf",
}

def check_fonts():
    if os.path.exists(os.path.join(FONTS_DIR, REQUIRED_FONT)):
        print("✅ Fonts found.")
        return

    print("\n⚠️  Fonts not found.")
    choice = input("   Download Atkinson Hyperlegible Mono now? (y/n): ").strip().lower()
    if choice == "y":
        import requests
        os.makedirs(FONTS_DIR, exist_ok=True)
        for name, url in FONT_URLS.items():
            r = requests.get(url)
            with open(os.path.join(FONTS_DIR, f"{name}.ttf"), "wb") as f:
                f.write(r.content)
            print(f"  Downloaded: {name}")
        print("✅ All fonts downloaded.")
    else:
        print("⚠️  Fonts skipped. Image generation will fail without fonts.")

# ============================================================
# STEP 6: Output Folders Check
# Ensures all required directories exist before the agent runs.
# Uses exist_ok=True so existing folders are not overwritten.
# Note: Per-episode subfolders are created dynamically by
# fetch.py — these are the base folders only.
# ============================================================

def check_folders():
    folders = [
        "input",
        "output/transcripts",
        "output/captions",
        "output/images",
        "output/pc_transcripts",  # Transcripts from PC audio uploads
        "assets/fonts",
    ]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
    print("✅ Output folders ready.")

# ============================================================
# STEP 7: Library Version Check
# Compares installed library versions against the latest
# available versions on PyPI.
#
# Process:
#   1. Use importlib.metadata to get installed version
#   2. Query PyPI JSON API for latest published version
#   3. Compare and build a list of outdated libraries
#   4. Offer a one-command update for all outdated libraries
#
# Runs silently on individual library fetch failures —
# a network issue with one library won't block the others.
# Skipped entirely if all libraries are up to date.
# ============================================================

def check_library_versions():
    import importlib.metadata
    import urllib.request
    import urllib.error

    print("\nChecking library versions...")

    # Maps pip package names to their importlib.metadata names
    # These can differ (e.g. PIL is installed as pillow)
    PACKAGE_METADATA_NAMES = {
        "openai-whisper": "openai-whisper",
        "feedparser":     "feedparser",
        "requests":       "requests",
        "google-genai":   "google-genai",
        "groq":           "groq",
        "pillow":         "Pillow",
        "plyer":          "plyer",
    }

    outdated = []

    for pip_name, metadata_name in PACKAGE_METADATA_NAMES.items():

        # ---- Get installed version ----
        try:
            installed = importlib.metadata.version(metadata_name)
        except importlib.metadata.PackageNotFoundError:
            # Library not installed — skip version check
            # launch.py's check_libraries() handles missing installs
            continue

        # ---- Query PyPI for latest version ----
        try:
            url = f"https://pypi.org/pypi/{pip_name}/json"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest = data["info"]["version"]
        except (urllib.error.URLError, KeyError, Exception):
            # Network issue or malformed response — skip silently
            continue

        # ---- Compare versions ----
        if installed != latest:
            outdated.append({
                "package":   pip_name,
                "installed": installed,
                "latest":    latest,
            })

    if not outdated:
        print("✅ All libraries are up to date.")
        return

    # ---- Display outdated libraries ----
    print(f"\n⚠️  {len(outdated)} outdated librar{'y' if len(outdated) == 1 else 'ies'} found:\n")
    for lib in outdated:
        print(f"   {lib['package']:<20} installed: {lib['installed']:<12} latest: {lib['latest']}")

    # ---- Offer one-command update ----
    choice = input("\n   Update all now? (y/n): ").strip().lower()
    if choice == "y":
        packages_to_update = [lib["package"] for lib in outdated]
        print("\nUpdating...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade"] + packages_to_update
        )
        print("✅ Libraries updated.")
    else:
        print("⚠️  Update skipped. Some features may behave unexpectedly with outdated libraries.")

# ============================================================
# NEW EPISODE DETECTOR
# Called on every launch after setup checks complete.
# Silently checks the first saved RSS feed for unprocessed
# episodes and stores results for main.py to display.
#
# Results are saved to output/new_episodes.json so main.py
# can read them without re-fetching the feed on every
# menu refresh.
#
# Runs silently — any failure returns without interrupting
# the launch sequence.
# ============================================================

def check_new_episodes_on_launch():
    try:
        # Import here to avoid circular imports at module level
        from scripts.fetch import check_new_episodes
        new = check_new_episodes()

        if not new:
            # Clear any stale new_episodes.json from previous run
            if os.path.exists("output/new_episodes.json"):
                os.remove("output/new_episodes.json")
            return

        # Save results for main.py to read and display
        os.makedirs("output", exist_ok=True)
        with open("output/new_episodes.json", "w") as f:
            json.dump(new, f, indent=2)

        print(f"\n🆕  {len(new)} new episode(s) detected in your RSS feed.")
        print("   Check the main menu for details.")

    except Exception:
        # Never interrupt launch for a detection failure
        pass

# ============================================================
# MAIN — Setup Runner
# Runs all checks in sequence on first launch.
# Skips checks on subsequent launches unless --setup is passed.
# Hands off to main.py menu after setup completes.
# ============================================================

def run_setup(force=False):
    # Skip all checks if setup already done and not forced
    if is_setup_complete() and not force:
        print("\n✅ Setup already complete. Launching Podcast Agent...")
        return

    print("\n" + "=" * 40)
    print("     🎙️  PODCAST AGENT — SETUP CHECK")
    print("=" * 40 + "\n")

    check_python_version()
    check_libraries()
    check_ffmpeg()
    check_api_keys()
    check_fonts()
    check_folders()

    # Mark setup complete so checks are skipped next time
    mark_setup_complete()

    print("\n" + "=" * 40)
    print("     ✅  All checks complete.")
    print("=" * 40)
    input("\nPress Enter to launch Podcast Agent...")

if __name__ == "__main__":
    # --setup flag forces all checks to re-run regardless of setup.json
    if "--setup" in sys.argv:
        run_setup(force=True)
    else:
        run_setup()

    # Hand off to main menu after setup
    from main import main
    main()