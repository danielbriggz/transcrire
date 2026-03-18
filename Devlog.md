# 🛠️ Podcast Agent — Developer Log

> Development session log. Entries are organised by phase in the order they occurred.
> All development conducted via Claude (claude.ai) in a single conversation session on March 15, 2026.

## 👤 Developer

**Daniel "Briggz" Adisa**

| Platform | Link |
|---|---|
| Instagram | https://instagram.com/danielbriggz |
| LinkedIn | https://linkedin.com/in/danieladisa |
| Twitter/X | https://x.com/danielBriggz |

---

## 📅 March 15, 2026

---

### Phase 1 — Project Conception

**Context:**
Conversation began after observing an example of an AI agent (built by "Chika") that automatically converted podcast content into TikTok-style short videos and posted them to social media platforms using Claude Code.

**Decisions made:**
- Understood the concept of an AI agent and its pipeline structure
- Identified the goal: build a similar agent tailored to own podcast
- Scoped the project away from video clips toward text-based content (tweets + images)
- Decided on a WhatsApp Channel as the primary distribution platform
- Confirmed free-only resource constraint
- Confirmed Nigerian context for platform/API availability considerations

---

### Phase 2 — Project Scoping + Architecture

**Features defined:**
- Agent transcribes podcast audio
- Agent selects notable segments from transcript
- Agent generates tweet-style captions with episode link
- Agent creates image versions of captions for Instagram/WhatsApp

**Distribution decision:**
- WhatsApp Business API explored but found to have costs
- WhatsApp Channels confirmed to have no public API for auto-posting
- Decided on **semi-automated pipeline** — agent handles all processing, user handles posting
- Full automation path noted for future development

**Pipeline defined:**
```
Fetch → Transcribe → Create Captions → Generate Images
```

---

### Phase 3 — Environment Setup

**Actions:**
- Confirmed development environment: Windows, Python installed, VS Code
- Created project folder structure via PowerShell terminal:
  ```
  podcast-agent/
  ├── input/
  ├── output/transcripts/
  ├── output/captions/
  ├── output/images/
  ├── scripts/
  └── config.py
  ```
- Created placeholder script files: `config.py`, `transcribe.py`, `caption.py`, `imagegen.py`
- Resolved terminal error: `type nul` command not working in PowerShell — switched to `New-Item`
- Installed initial libraries: `openai-whisper`, `pillow`

---

### Phase 4 — `transcribe.py` — Initial Build

**Features implemented:**
- Script scans `input/` folder for audio files
- Loads OpenAI Whisper `base` model
- Transcribes selected audio file
- Saves transcript as `.txt` to `output/transcripts/`
- Displays elapsed transcription time

**Bugs resolved:**
- `FileNotFoundError` on transcription — identified missing `ffmpeg` dependency
- Guided through ffmpeg download, extraction and PATH configuration on Windows
- `ModuleNotFoundError: whisper` after activating `.venv` — reinstalled Whisper inside virtual environment
- `FP16 not supported on CPU` warning — confirmed non-breaking, explained CPU/GPU fallback

---

### Phase 5 — `fetch.py` — Initial Build

**Features implemented:**
- Prompts for RSS feed URL, season number and episode number
- Parses RSS feed using `feedparser`
- Matches episode by `itunes_season` and `itunes_episode` fields
- Selective fetch menu:
  - `1` Audio only
  - `2` Cover art only
  - `3` Spotify link only
  - `4` All
- Downloads audio to `input/` folder
- Downloads episode cover art to `output/images/`
- Saves episode metadata (title + Spotify link) to `output/metadata.json`
- Execution time displayed on completion

**Bugs resolved:**
- `OSError: Invalid argument` on filename — Windows-illegal characters in episode title (e.g. `|`, `"`) — implemented filename sanitizer stripping all restricted characters
- Cover art fetching initially pulled podcast-level art instead of episode-level — fixed by checking `match.get("image", {}).get("href")` on the entry directly (confirmed via debug block)
- Debug block removed after issue resolved

**Features added during build:**
- Audio filename format set to `{episode title} - S{season}E{episode}.mp3`
- RSS feed persistent storage introduced (`feeds.json`) — podcast name auto-fetched from feed, no manual naming required
- Spotify episode link retrieval added to fetch options
- Execution time tracking added (`time` module)
- Time display improved to show minutes when elapsed > 60 seconds (`utils.py`)

---

### Phase 6 — `utils.py` — Created

**Features implemented:**
- `format_time(seconds)` utility function
- Returns `Xm Ys` format for values over 60 seconds
- Returns `X.Xs` format for values under 60 seconds
- Imported and used across `fetch.py`, `transcribe.py`, `caption.py`, `imagegen.py`

---

### Phase 7 — `transcribe.py` — Update 1

**Features updated:**
- Updated to detect most recently downloaded file automatically (option `0`)
- Multi-file selection menu added for `input/` folder
- Execution time now uses `format_time()` from `utils.py`

---

### Phase 8 — `caption.py` — Initial Build

**Features implemented:**
- Loads transcript from `output/transcripts/`
- Pulls Spotify link from `output/metadata.json` — falls back to manual input if not found
- Multi-platform caption generation via Google Gemini API:
  - Twitter: short, punchy, under 250 characters
  - LinkedIn: professional, 3-4 sentences, ends with a question
  - Facebook: warm, conversational, encourages discussion
- Platform selection menu — choose one or all
- Captions saved per platform to `output/captions/`
- Execution time displayed

**Setup actions:**
- Obtained free Gemini API key from Google AI Studio
- Installed `google-generativeai` library
- Added `GEMINI_API_KEY` to `config.py`

**Bugs resolved:**
- `models/gemini-1.5-flash is not found` — updated model to `gemini-2.0-flash`, then further updated to `gemini-2.5-flash`
- `FutureWarning` from deprecated `google.generativeai` package — migrated to `google.genai` package with updated client initialisation pattern

**Features added during build:**
- Caption transcript always prompts for selection — never silently auto-selects
- Caption preview not yet implemented at this stage (added later)

---

### Phase 9 — `imagegen.py` — Initial Build

**Features implemented:**
- Loads episode cover art from `output/images/`
- Loads captions from `output/captions/` — 3 Twitter, 2 Facebook
- Blurs cover art and applies dark overlay as background
- Centres quote text vertically with word wrap
- White text with subtle drop shadow for readability
- Strips links and numbering from captions before rendering
- Generates square (1080×1080) images only
- Saves quote cards to `output/images/`
- Execution time displayed

**Font setup:**
- Selected Atkinson Hyperlegible Mono from Google Fonts
- Retrieved all font weight URLs directly from Google Fonts CSS embed link
- Downloaded all 7 weights (ExtraLight through ExtraBold) to `assets/fonts/`
- Font size set to 34px

**Features added during build:**
- Background brightness detection via greyscale average — auto-selects font weight:
  - Avg brightness < 100 (dark) → SemiBold (600)
  - Avg brightness ≥ 100 (light) → Medium (500)
- Portrait format option added then removed — square only retained

---

### Phase 10 — `main.py` — Initial Build

**Features implemented:**
- Central menu hub linking all four scripts
- Menu options: Fetch Episode, Transcribe, Create Captions, Generate Images, Exit
- After each step: prompt to continue to next step or return to main menu
- After Generate Images: returns to main menu (end of chain)
- Error handling wraps each script call

**Bugs resolved:**
- Scripts running on import (skipping menu) — identified standalone function calls at bottom of each script — removed from all four files
- `KeyboardInterrupt` on launch — identified as accidental `Ctrl+C`, not a code issue

---

### Phase 11 — `transcribe.py` — Update 2 (Groq Integration)

**Features implemented:**
- Dual transcription mode selection:
  - `1` Fast — Groq API (cloud, requires internet)
  - `2` Offline — Whisper `small` model (local, no internet)
- Groq mode compresses audio to 64kbps mono via ffmpeg before upload
- Auto-fallback to offline mode if compressed file exceeds Groq's 25MB limit
- Compressed file deleted after transcription

**Bugs resolved:**
- `Error 413: Request Entity Too Large` — implemented ffmpeg audio compression before Groq upload
- `ModuleNotFoundError: pyaudioop` — caused by Python 3.13 incompatibility with `pydub` — replaced `pydub` with direct `ffmpeg` subprocess call, uninstalled `pydub`

---

### Phase 12 — `launch.py` — Initial Build

**Features implemented:**
- Python version check — warns if 3.13+, opens download page and prints instructions if user declines to proceed
- Required libraries check — detects missing packages, offers mass install
- ffmpeg availability check — provides step-by-step installation guidance if missing
- API key check — prompts for Gemini and Groq keys if not configured
- Font availability check — offers to download all Atkinson Hyperlegible Mono weights if missing
- Output folder creation — creates all required folders if absent
- Setup completion flag — saves `setup.json` after first successful setup
- Re-check toggle — `python launch.py --setup` forces re-run of all checks

**Features added during build:**
- Python version warning updated: browser only opens if user chooses not to proceed
- API key validation added — both Gemini and Groq keys tested with a live call before saving
  - Invalid key triggers retry prompt before skipping
  - Keys only saved to `config.py` once confirmed valid

---

### Phase 13 — Category A Features

*Ten features scoped and prioritised across 5 categories. Category A (Urgent and Doable) implemented first.*

---

#### `fetch.py` — Category A Updates

**Feature 1 — Output organisation by episode:**
- Per-episode subfolder created at `output/{safe_title} - S{season}E{episode}/`
- Subfolders: `transcripts/`, `captions/`, `images/`
- Episode folder paths saved to `output/metadata.json` for reference by all downstream scripts

**Feature 5 — Episode history log:**
- `history.json` created and updated after every successful fetch
- Stores: episode title, season, episode number, date and time of processing
- Duplicate detection: checks `history.json` before fetching
- If duplicate found: lists previous processing dates, prompts to proceed or abort

**Feature 4 — Friendly error messages:**
- RSS feed load failure: actionable message with internet connection guidance
- Audio download failure: specific `ConnectionError` and generic exception handling
- Cover art download failure: specific message per error type

**Additional fix:**
- `podcast_name` now returned from `load_feed()` and saved to `metadata.json`
- Enables main menu to display podcast name on launch

---

#### `transcribe.py` — Category A Updates

**Feature 1 — Output organisation by episode:**
- Transcript save path now reads episode subfolder from `metadata.json`
- Removed `TRANSCRIPT_FOLDER` from config imports
- Graceful warning if metadata missing — directs user to run Fetch first

**Feature 4 — Friendly error messages:**
- ffmpeg not found: directs user to run `python launch.py --setup`
- ffmpeg compression failure: specific return code check
- Groq invalid API key: directs to setup
- Groq rate limit: clear wait-and-retry guidance
- Groq file too large: auto-fallback to offline with message
- Whisper file not found: specific message
- Empty transcript output: caught before attempting file save

---

#### `caption.py` — Category A Updates

**Feature 1 — Output organisation by episode:**
- Transcript loaded from episode subfolder via `metadata.json`
- Captions saved to episode subfolder via `metadata.json`
- Removed `TRANSCRIPT_FOLDER` and `CAPTIONS_FOLDER` from config imports

**Feature 2 — Caption preview and approve/regenerate:**
- After generation, each platform's captions printed in full as a preview
- User prompted with three options:
  - `1` Approve and save
  - `2` Regenerate all (re-calls Gemini with same prompt)
  - `3` Skip platform
- File only written to disk after explicit approval

**Feature 4 — Friendly error messages:**
- Gemini invalid API key: directs to setup
- Gemini rate limit: wait-and-retry guidance
- Gemini model not found: model name change warning
- Gemini client initialisation failure: caught separately

---

#### `imagegen.py` — Category A Updates

**Feature 1 — Output organisation by episode:**
- Cover art and captions loaded from episode subfolder via `metadata.json`
- Quote cards saved to episode subfolder via `metadata.json`
- Removed `CAPTIONS_FOLDER` and `IMAGES_FOLDER` from config imports

**Feature 4 — Friendly error messages:**
- Cover art file not found: specific message
- Cover art open/resize failure: caught separately
- Font file missing: directs user to run `python launch.py --setup`
- Individual quote card generation errors caught without stopping the whole batch
- Success/fail count printed at completion

---

#### `main.py` — Category A Updates

**Feature 3 — Status dashboard:**
- Active podcast name displayed on launch (from `metadata.json`)
- Active episode title, season and episode displayed once an episode is fetched
- Long titles truncated at 28 characters
- Status indicators next to each menu item:
  - ✅ Step complete (output files detected)
  - ⬜ Step not yet done
- Status checks per step:
  - Fetch: `episode_paths` present in metadata
  - Transcribe: `.txt` file exists in episode transcripts folder
  - Captions: `_captions.txt` file exists in episode captions folder
  - Images: `_quote` `.jpg` file exists in episode images folder
- Status refreshes automatically on every return to menu
- Indicators reset automatically when a new episode is detected

---

### Phase 14 — Timestamped Transcription + Reference Lists

#### `transcribe.py` — Timestamped Transcription

**Features implemented:**
- New transcript type selection after mode choice:
  - `1` Plain text — no timestamps (original behaviour)
  - `2` Segment level — timestamped by phrase `[HH:MM:SS - HH:MM:SS] text`
  - `3` Word level — timestamped by individual word `[HH:MM:SS] word`
- Groq: uses `verbose_json` response format with `timestamp_granularities` per type
- Whisper: uses `word_timestamps=True` for word level
- Each type saved to a distinct file:
  - `transcript.txt` — plain
  - `transcript_segments.txt` — segment level
  - `transcript_words.txt` — word level
- Timestamp formatter converts raw seconds to `HH:MM:SS`

#### `caption.py` — Reference List Generation

**Features implemented:**
- Transcript selection detects timestamped files and lists them with ⏱️ label
- Timestamped transcripts automatically preferred in selection order
- After caption approval, if a timestamped transcript was used:
  - Separate Gemini call generates a `_references.txt` file per platform
  - Reference list maps each caption to its source timestamp range and quote
- `build_prompt()` simplified — timestamp instructions removed from caption prompt to keep captions clean

**Example reference list output:**
```
CAPTION REFERENCES — TWITTER
========================================

Caption 1: [00:04:21 - 00:04:35] "Christians are selective about who deserves empathy..."
Caption 2: [00:11:02 - 00:11:19] "Empathy isn't a feeling, it's a discipline..."
```

---

### Phase 15 — README + Documentation

**Actions:**
- `README.md` created and updated iteratively across the session
- Final version covers:
  - Full project structure with per-episode subfolder example
  - All scripts documented with feature lists and example outputs
  - Setup instructions including font download script
  - `launch.py` setup check documentation
  - Typical workflow
  - Full output file tree example per episode
  - Planned full automation phase noted

---

### Phase 16 — Code Comments Pass

**All scripts annotated with structured comments covering:**
- File-level header: purpose, developer credit, usage notes
- Section dividers for each major function group
- Inline comments on non-obvious logic
- Parameter and return value notes on key functions
- Error handling explanations

**Files commented:**
- `config.py` — folder paths, API key descriptions, setup notes
- `launch.py` — full setup flow, each check step, flag handling
- `main.py` — menu registry, pipeline sequence, status logic
- `fetch.py` — feed loader, history, subfolder creator, fetch flow
- `transcribe.py` — audio picker, timestamp formatters, Groq + Whisper flows
- `caption.py` — platform registry, transcript loader, Gemini calls, preview loop
- `imagegen.py` — font selector, background analysis, word wrap, rendering
- `utils.py` — time formatter with docstring examples

---

### Phase 17 — Code Audit + `utils.py` Refactor

**Audit findings:**
- `load_metadata()` duplicated across `transcribe.py`, `caption.py` and `imagegen.py`
- `METADATA_PATH` constant defined separately in every script
- "Most recent file" selection logic repeated in multiple scripts
- Dead config imports in some scripts (`TRANSCRIPT_FOLDER`, `CAPTIONS_FOLDER`)
- `sys.path.append` block repeated in every script in `scripts/`
- Inconsistent error message spacing (`⚠️  ` vs `⚠️ `)

**Changes implemented — `utils.py` refactor (Phase 1):**

`utils.py`:
- Added `METADATA_PATH` as a centralised constant
- Added shared `load_metadata()` with three-stage validation:
  - Stage 1: checks `metadata.json` exists
  - Stage 2: catches JSON parse errors
  - Stage 3: validates `episode_paths` key is present
- Added `json` and `os` imports to support new functions

`transcribe.py`:
- Removed local `load_episode_paths()` function
- Removed local `METADATA_PATH` constant
- Imported `load_metadata` from `utils.py`
- Updated `transcribe()` to call shared `load_metadata()`

`caption.py`:
- Removed local `load_metadata()` function
- Removed local `METADATA_PATH` constant
- Imported `load_metadata` from `utils.py`
- Existing `generate_captions()` call unchanged — drop-in replacement

`imagegen.py`:
- Removed local `load_metadata()` function
- Removed local `METADATA_PATH` constant
- Imported `load_metadata` from `utils.py`
- Existing `generate_images()` call unchanged — drop-in replacement

---

### Phase 18 — Category C Features

#### `caption.py` — Single Caption Regeneration (Feature 8)

**Features implemented:**
- Added option `4` — "Edit an individual caption" to `preview_and_approve()`
- New `regenerate_single_caption()` function:
  - Parses full captions text into individually numbered entries
  - Displays each caption with an 80-character preview for easy identification
  - Builds a targeted Gemini prompt to replace only the selected caption in matching style and format
  - Splices replacement back into full captions text
  - Renumbers all captions cleanly after replacement
  - Loops back to preview so user can review the change
- `spotify_link` passed through to `preview_and_approve()` so replacement captions include the correct episode link

---

#### `imagegen.py` — Post-Generation Image Review (Feature 7)

**Features implemented:**
- New `review_images()` function:
  - Accepts a list of generated image metadata dicts
  - Prints a numbered summary of all images with platform, index and caption preview
  - Reviews each image individually:
    - `1` Approve
    - `2` Regenerate with lighter overlay (opacity 120)
    - `3` Skip and delete from disk
  - Second regeneration attempt uses darker overlay (opacity 200)
  - Prints final confirmed output list on completion
- `make_quote_card()` updated to accept optional `overlay_opacity` parameter (default `160`)
- `generate_images()` updated to:
  - Collect all generated image metadata into a `generated` list
  - Offer optional review after generation completes
  - Pass full image context to `review_images()` for regeneration support

---

### Phase 19 — Category D Features

#### `fetch.py` — New Episode Detection (Feature 9)

**Features implemented:**
- `get_latest_processed()` — reads `history.json`, sorts by date string descending, returns most recent entry
- `check_new_episodes()` — silently fetches first saved RSS feed, compares all entries against history using a set for O(1) lookup, returns list of unprocessed episodes with title, season, episode and link
- Both functions fail silently — return `None` or `[]` rather than printing errors

---

#### `launch.py` — Library Version Checker + New Episode Detection (Features 9 & 10)

**Features implemented:**
- `check_library_versions()`:
  - Uses `importlib.metadata` to get installed version per library
  - Queries PyPI JSON API for latest version
  - Compares installed vs latest — builds outdated list
  - Displays formatted table with installed and latest versions
  - Offers one-command `pip install --upgrade` for all outdated libraries
  - Runs silently per library — network failure on one doesn't block others
  - Added to `run_setup()` between `check_libraries()` and `check_ffmpeg()`
- `check_new_episodes_on_launch()`:
  - Calls `fetch.py`'s `check_new_episodes()` silently on every launch
  - Saves results to `output/new_episodes.json` for `main.py` to consume
  - Clears `new_episodes.json` if no new episodes found — prevents stale data
  - Prints launch notification if new episodes detected
  - Called in `if __name__ == "__main__":` block after `run_setup()`

---

#### `main.py` — New Episode Notification + Fetch Shortcut (Feature 9)

**Features implemented:**
- `load_new_episodes()` — reads `output/new_episodes.json` silently, returns `[]` on any failure
- `jump_to_fetch()` — displays episode details, removes episode from `new_episodes.json` and proceeds to fetch step
- `print_menu()` updated to display new episode notification banner below the menu
- `main()` updated:
  - Loads new episodes on every loop iteration
  - `N` input added as shortcut to fetch a new episode
  - Single new episode jumps directly — multiple shows a selection menu

---

### Phase 20 — Project Summary + Feature Audit

**Full project summary produced covering:**
- All entry points and how to run the agent
- Every script's purpose and feature set
- All tools, APIs and libraries in use
- Complete output file structure per episode

---

### Phase 21 — `pipeline.py` — Strategy Design

**Initial strategy proposed:**
- Single-command pipeline running fetch → transcribe → caption → images unattended
- Config-driven, bypassing interactive menus

**Concern raised by developer:**
- User control over process decisions would be eliminated
- Risk of pipeline being too opinionated without user consent

**Revised strategy adopted — two templated modes:**

*Mode 1: Full Auto*
- User provides only season + episode number
- All other decisions use smart defaults

*Mode 2: Guided Auto*
- User prompted once upfront for all preferences
- Pipeline runs uninterrupted after configuration

**Pitfalls identified and addressed:**

| # | Pitfall | Severity |
|---|---|---|
| 1 | Silent Groq fallback to slow Whisper | Medium |
| 2 | Bad transcript → bad captions | Medium |
| 3 | Episode not found kills pipeline silently | High |
| 4 | Mid-pipeline errors in Guided Auto | Medium |
| 5 | Duplicate detection requires user input | High |
| 6 | `_pending_review` backlog unnoticed | Low |
| 7 | Guided Auto missing decision points | High |

**Strategy categorised and approved:**

*High (Necessary):* Mode selection, episode not found hard stop, duplicate handling, input() audit, end-of-run summary, `pipeline_run.log`

*Medium (Important):* Groq fallback notification, `_pending_review` suffix, backlog warning, Guided Auto decision map, mid-pipeline stage skipping

*Low (Optional):* `pipeline_config.json` template, inline CLI arguments, completion notification, estimated run time display

---

### Phase 22 — `cleanup.py` — Created

**Purpose:**
Standalone utility script that clears all files from `input/` and `output/` folders without deleting the folder structure itself.

**Features implemented:**
- Deletes all files and subfolders inside `input/` and `output/`
- Preserves the folders themselves — ready for a new episode immediately after
- Requires typing `yes` in full to confirm — prevents accidental deletion
- Reports every deleted file and folder path individually
- Handles errors per item — one undeletable file does not stop the rest
- Prints summary: total files deleted, total folders deleted
- Fully standalone — no imports from other project scripts

---

### Phase 23 — `pipeline.py` — Feature Breakdown

**High priority features broken down into main tasks and sub-tasks:**

| Feature | Main Task | Scripts |
|---|---|---|
| 1. Mode selection | Mode menu, PipelineConfig, Full Auto defaults, Guided Auto decision map | `pipeline.py` |
| 2. Episode not found | RSS validation, log entry, user message, clean exit | `pipeline.py` |
| 3. Duplicate handling | Per-mode defaults, config flag, refactor check_duplicate() | `pipeline.py`, `fetch.py` |
| 4. Audit input() calls | Map all calls, define config keys, refactor core functions | All scripts, `pipeline.py` |
| 5. End-of-run summary | StageResult structure, collect per stage, print summary | `pipeline.py` |
| 6. pipeline_run.log | Run header, per-stage entries, final entry | `pipeline.py` |

**Implementation order agreed:**
`fetch.py` → `transcribe.py` → `caption.py` → `imagegen.py` → `pipeline.py`

---

### Phase 24 — Pipeline Refactoring: All Core Scripts

All four core scripts refactored to accept an optional `config` parameter. When `config` is provided, all `input()` calls are bypassed and values are read from the config dict instead. When `config=None`, original interactive behaviour is fully preserved.

#### `fetch.py`

`check_duplicate(season, episode, config=None)`:
- Pipeline mode: uses `config["skip_duplicates"]` flag — no prompt
- Interactive mode: original prompt behaviour unchanged

`load_feed(config=None)`:
- Pipeline mode: selects podcast by `config["podcast_name"]` directly from `feeds.json`
- Interactive mode: original saved list / new podcast flow unchanged

`fetch_episode(config=None)`:
- Pipeline mode: season, episode and fetch choice all read from config
- Interactive mode: all original prompts unchanged

#### `transcribe.py`

`pick_audio(config=None)`:
- Pipeline mode: uses `config["audio_filename"]` if specified, falls back to most recent
- Interactive mode: original file listing and selection unchanged

`transcribe(config=None)`:
- Pipeline mode: mode and transcript type read from config
- Groq fallback sets `config["groq_fallback_triggered"] = True` for pipeline logging
- Interactive mode: all original prompts unchanged

#### `caption.py`

`load_transcript(transcript_folder, config=None)`:
- Pipeline mode: selects transcript by `config["transcript_type"]` directly
- Falls back gracefully through segments → words → plain → any
- Interactive mode: original selection menu unchanged

`load_spotify_link(metadata, config=None)`:
- Pipeline mode: warns and continues with empty string if no link found
- Interactive mode: original manual input fallback unchanged

`generate_captions(config=None)`:
- Pipeline mode: platform selection from `config["caption_platforms"]`
- Captions saved with `_pending_review` suffix
- Returns `output_paths` list for pipeline summary
- Interactive mode: original preview/approve/regenerate flow unchanged

#### `imagegen.py`

`load_cover_art(images_folder, config=None)`:
- Pipeline mode: always uses most recently downloaded cover art
- Interactive mode: original selection unchanged

`load_captions(captions_folder, platform, count, config=None)`:
- Pipeline mode: prefers `_pending_review` files, falls back to approved files
- Interactive mode: original selection unchanged

`generate_images(config=None)`:
- Pipeline mode: skips post-generation review, returns image paths for summary
- Interactive mode: original review prompt unchanged

---

### Phase 25 — `pipeline.py` — Created

**Full one-command pipeline runner implementing all High priority features.**

**Core structures:**

`PipelineConfig` — central dict with all decision values and smart defaults for Full Auto.

`StageResult` — lightweight dict tracking stage, status, output_paths, reason and timestamp. Status values: completed / skipped / failed.

**Logger (`pipeline_run.log`):**
- Run header, per-stage entries and footer written on every run
- Appends to existing log — all runs preserved

**Mode builders:**

`build_full_auto_config()` — prompts only for podcast, season and episode. All other decisions use smart defaults.

`build_guided_auto_config()` — walks through every decision point upfront, prints confirmation summary, runs uninterrupted after confirmation.

**Pre-run checks:**
- `check_pending_review_backlog()` — warns if previous pipeline captions haven't been reviewed
- `validate_episode()` — hard stop with log entry if episode not found in RSS feed
- `check_pipeline_duplicate()` — Full Auto skips silently, Guided Auto uses pre-configured flag

**Pipeline runner (`run_pipeline()`):**
- Fetch and transcribe failures are critical hard stops
- Caption and image failures logged and skipped
- Collects StageResult after every stage

**CLI support:**
```bash
python pipeline.py
python pipeline.py --auto --season 6 --episode 5
python pipeline.py --auto --season 6 --episode 5 --podcast "My Podcast"
```

---

### Phase 26 — `run_all.py` renamed to `launch.py`

**Reason:**
`run_all.py` no longer accurately describes the file's purpose given that `pipeline.py` now exists as the full pipeline runner. `launch.py` better reflects its actual role as a setup checker and interactive menu launcher.

**Changes:**
- File renamed from `run_all.py` to `launch.py`
- All script error message references updated: `python run_all.py --setup` → `python launch.py --setup`
- Header comment in `launch.py` updated
- `README.md` updated — all references replaced
- `DEVLOG.md` updated — all references replaced

---

### Phase 27 — Medium Priority Pipeline Features + Review Menu

#### `transcribe.py` — Groq Fallback Notification (Feature 7)

**Changes:**
- `transcribe_groq()` now returns a `(transcript, reason)` tuple when falling back internally
  - `"file_too_large"` — compressed file still exceeds 25MB
  - `"groq_api_failure"` — Groq API call failed
- `transcribe()` detects tuple return and prints immediate in-run notice at point of fallback
- `config["groq_fallback_reason"]` set alongside `config["groq_fallback_triggered"]` for pipeline logging
- Interactive mode users also see the fallback notice

---

#### `pipeline.py` — Medium Priority Updates

**Feature 7 — Groq fallback notification:**
- `log_stage()` updated to write Groq fallback as a distinct log entry separate from the stage result
- `print_summary()` Groq fallback notice expanded with specific reason and time impact message
- Transcribe `StageResult` now carries `fallback` dict with reason for distinct logging
- `config["groq_fallback_reason"]` added to `make_pipeline_config()` defaults

**Feature 8 — Expanded pending review backlog:**
- `scan_pending_review_backlog()` replaces inline backlog check — scans entire `output/` tree
- `check_pending_review_backlog()` updated to group results by episode with clear display
- Post-run backlog check re-scans full `output/` folder after every run
- `--review` CLI flag added — lists all pending files without starting a run

**Feature 8 — Review from pipeline menu:**
- `review_pending_captions()` added — lists all pending files grouped by episode with numbers
- User can mark a single file or all files as reviewed
- Marking removes `_pending_review` suffix — file becomes the approved version
- List refreshes after each file is marked — remaining count stays accurate
- `R` option added to pipeline menu — only visible when pending files exist
- Pending count refreshes after every run and every review session

**Feature 9 — Guided Auto edge case handling:**
- `check_internet()` helper added — tests connectivity via socket before Groq is used
- `preflight_validation()` added — runs after Guided Auto configuration confirms:
  - Groq + no internet → auto-switches to offline Whisper, sets fallback flags
  - Missing/placeholder API keys → warns before run starts
  - Groq API key missing → auto-switches to offline
- Cover art absence logged as a note on fetch stage — does not fail the run
- Caption platform partial success tracked and noted in stage result

---

### Phase 28 — Low Priority Pipeline Features — `launch.py`

#### `launch.py` — plyer Added to Library Checks (Feature 11)

**Changes:**
- `plyer` added to `REQUIRED_LIBRARIES` — detected and offered for mass install if missing
- `plyer` added to `PACKAGE_METADATA_NAMES` in `check_library_versions()` — version checked against PyPI on every setup run

---

### Phase 29 — Low Priority Pipeline Features — `pipeline.py`

#### `pipeline.py` — Low Priority Updates (Features 10, 11, 12)

**Feature 12 — Estimated run time display:**
- `parse_last_run_duration()` — parses `pipeline_run.log` using regex to find the most recent completed run's duration
- `display_estimated_run_time()` — displays estimate before pipeline starts, shows first-run notice if no log exists
- `print_summary()` updated — shows actual vs estimated duration side by side after run completes

**Feature 11 — Completion notification:**
- `send_completion_notification()` added — triggers Windows toast via `plyer` on Full Auto completion
- Toast includes episode identifier, stage outcome summary and total duration
- Falls back to terminal bell (`\a`) if `plyer` not installed
- Only fires in Full Auto mode — Guided Auto user is already watching the terminal
- Never interrupts the run if notification fails

**Feature 10 — Saved config template:**
- `CONFIG_TEMPLATE_PATH` constant set to `pipeline_config.json`
- `RUNTIME_KEYS` set defined — keys stripped before saving template
- `save_config_template()` — strips runtime-only keys, saves clean config to `pipeline_config.json`
- `load_config_template()` — loads template and resets runtime keys to defaults
- Guided Auto offers to save template immediately after confirming configuration
- `T` menu option added — only visible when `pipeline_config.json` exists, displays saved podcast + settings
- `--config` CLI flag added — loads template and prompts only for season + episode

---

## 📊 Session Summary

| File | Status | Updates |
|---|---|---|
| `launch.py` | ✅ Complete | Setup checks, validation, re-check toggle, version checker, new episode detection, plyer added, comments |
| `main.py` | ✅ Complete | Menu, status dashboard, episode display, new episode banner, fetch shortcut, comments |
| `fetch.py` | ✅ Complete | RSS, history, subfolders, error handling, new episode detection, pipeline refactor, comments |
| `transcribe.py` | ✅ Complete | Groq + Whisper, timestamps, error handling, pipeline refactor, fallback notification, comments |
| `caption.py` | ✅ Complete | Gemini, platforms, preview, single caption regeneration, references, pipeline refactor, comments |
| `imagegen.py` | ✅ Complete | Quote cards, brightness detection, post-generation review, pipeline refactor, comments |
| `pipeline.py` | ✅ Complete | Full Auto + Guided Auto, all priority features, review menu, estimated run time, notifications, config template |
| `utils.py` | ✅ Complete | Time formatter, metadata loader, METADATA_PATH constant |
| `config.py` | ✅ Complete | Comments added |
| `cleanup.py` | ✅ Complete | Standalone cleanup utility |
| `README.md` | ✅ Complete | Full documentation |
| `DEVLOG.md` | ✅ This file | |

---

## 🗂️ Pending (Future Sessions)

| Priority | Feature |
|---|---|
| Category B | Transcription resume from checkpoint |
| Planned | Auto-posting to WhatsApp broadcast list |
| Planned | Scheduled runs triggered by new RSS episodes |