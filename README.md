# 🎙️ Podcast Agent

> A semi-automated content pipeline that transforms podcast episodes into platform-ready social media assets — captions, quote cards and timestamp reference lists — with minimal manual effort.

---

## 👤 Developer

**Daniel "Briggz" Adisa**

| Platform | Link |
|---|---|
| Instagram | https://instagram.com/danielbriggz |
| LinkedIn | https://linkedin.com/in/danieladisa |
| Twitter/X | https://x.com/danielBriggz |

---

## 📌 Overview

Podcast Agent is a Python-based CLI tool built for solo podcasters who want to repurpose episode content for social media without spending hours on manual editing and formatting.

Given a podcast episode, the agent:

1. **Fetches** the episode audio, cover art and Spotify link directly from your RSS feed
2. **Transcribes** the audio — locally via Whisper or via the cloud using Groq
3. **Generates** platform-specific social media captions using Google Gemini
4. **Creates** styled quote card images using the episode cover art as a background

The pipeline can be run interactively step by step, or fully automated in a single command via `pipeline.py`.

**Built entirely with free tools and APIs.** Designed for a Nigerian podcaster on Windows, with practical constraints in mind.

---

## 🗂️ Project Structure

```
podcast-agent/
│
├── input/                          # Downloaded audio files
│
├── output/
│   └── {Episode Title} - SxEx/     # Per-episode subfolder (auto-created)
│       ├── transcripts/             # Plain or timestamped transcripts
│       ├── captions/                # Captions + reference lists
│       └── images/                  # Cover art + quote card images
│   ├── metadata.json                # Active episode info
│   └── new_episodes.json            # Unprocessed RSS episodes (auto-generated)
│
├── assets/
│   └── fonts/                       # Atkinson Hyperlegible Mono weights
│
├── scripts/
│   ├── fetch.py                     # RSS feed fetcher
│   ├── transcribe.py                # Audio transcriber
│   ├── caption.py                   # Caption generator
│   ├── imagegen.py                  # Quote card generator
│   └── utils.py                     # Shared utilities
│
├── feeds.json                       # Saved RSS feeds
├── history.json                     # Episode processing history
├── setup.json                       # First-time setup flag
├── pipeline_run.log                 # Automated pipeline run log
├── launch.py                        # Setup checker + interactive launcher
├── main.py                          # Interactive main menu
├── pipeline.py                      # Full one-command pipeline runner
├── cleanup.py                       # Input/output folder cleaner
└── config.py                        # API keys + folder paths
```

---

## 🚀 Entry Points

| Command | What it does |
|---|---|
| `python launch.py` | Run setup checks + launch interactive menu |
| `python launch.py --setup` | Force re-run all setup checks |
| `python pipeline.py` | Launch pipeline with mode selection |
| `python pipeline.py --auto --season 6 --episode 5` | Full Auto — prompts for podcast only |
| `python pipeline.py --auto --season 6 --episode 5 --podcast "My Podcast"` | Fully non-interactive |
| `python pipeline.py --config --season 6 --episode 5` | Load saved config template |
| `python pipeline.py --review` | List all pending review caption files |
| `python cleanup.py` | Delete all files in `input/` and `output/` |

---

## ⚙️ Setup

### Requirements

- Python 3.10–3.12 *(3.13 has known audio library issues)*
- VS Code (recommended)
- ffmpeg installed and added to system PATH

### Dependencies

```bash
pip install openai-whisper feedparser requests google-genai groq pillow plyer
```

### API Keys

Add both keys to `config.py`:

```python
GEMINI_API_KEY = "your-gemini-api-key-here"
GROQ_API_KEY   = "your-groq-api-key-here"
```

| Key | Free tier at |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | https://console.groq.com |

> `launch.py` will prompt for and validate both keys automatically on first run.

---

## 🛠️ Features

### `launch.py` — Setup Checker

Runs on first launch, skipped on subsequent runs unless `--setup` is passed.

- Python version check — warns if 3.13+, opens download page if user declines to proceed
- Missing library detection — offers mass install
- Library version check — compares installed vs latest PyPI versions, offers one-command update
- ffmpeg check — step-by-step installation guidance if missing
- API key validation — live test call before saving to `config.py`
- Font auto-download — all 7 Atkinson Hyperlegible Mono weights
- Output folder creation
- New episode detection — silently checks RSS feed on every launch, notifies in main menu

---

### `main.py` — Interactive Menu

```
========================================
        🎙️  PODCAST AGENT
========================================
  📻 S6E5 — V073 Christians Lack Empa...
----------------------------------------
  1. ✅ Fetch Episode
  2. ✅ Transcribe
  3. ✅ Create Captions
  4. ⬜ Generate Images
----------------------------------------
  0.    Exit
========================================

  🆕  1 new episode(s) available:
     1. S6E6 — V074 | The Problem With...

  N.  Fetch a new episode from the list above
```

- Displays podcast name on launch, episode details once fetched
- Status indicators (✅ / ⬜) per pipeline step — refreshes on every return
- New episode notification banner for unprocessed RSS episodes
- `N` shortcut to jump directly to fetching a new episode
- Continue/return prompt after each step

---

### `fetch.py` — Episode Fetcher

- Saves RSS feeds persistently in `feeds.json` — podcast name fetched automatically, no manual naming
- Targets specific episodes by season + episode number
- Duplicate detection via `history.json` — warns before reprocessing
- Selective fetch: audio only, cover art only, Spotify link only, or all
- Creates per-episode output subfolder automatically
- Saves full episode metadata to `output/metadata.json`
- Logs every processed episode to `history.json` with date and time

---

### `transcribe.py` — Audio Transcriber

**Two modes:**

| Mode | Speed | Internet |
|---|---|---|
| Groq API | Fast | Required |
| Whisper small | Slower | Not required |

**Three transcript types:**

| Type | Output |
|---|---|
| Plain | Full transcript, no timestamps |
| Segment level | `[HH:MM:SS - HH:MM:SS] phrase` |
| Word level | `[HH:MM:SS] word` inline |

- Groq mode compresses audio via ffmpeg before upload — auto-fallback to Whisper if file exceeds 25MB
- Timestamped transcripts saved with `_segments` or `_words` suffix
- Saves to per-episode transcripts subfolder

---

### `caption.py` — Caption Generator

**Supported platforms:**

| Platform | Style | Count |
|---|---|---|
| Twitter | Short, punchy, under 250 characters | 5 |
| LinkedIn | Professional, 3-4 sentences, reflective question | 5 |
| Facebook | Warm, conversational, encourages discussion | 5 |

- Detects and prefers timestamped transcripts — labelled ⏱️ in selection menu
- Preview + approve before saving
- Four actions per platform:
  - `1` Approve and save
  - `2` Regenerate all
  - `3` Skip platform
  - `4` Edit an individual caption
- Single caption regeneration — Gemini replaces only the selected caption in matching style
- Generates a `_references.txt` file per platform when a timestamped transcript is used — maps each caption to its source timestamp for clip editing

---

### `imagegen.py` — Quote Card Generator

- Generates square (1080×1080) images — 3 Twitter + 2 Facebook per episode
- Episode cover art as background: blurred + dark overlay
- Auto font weight selection based on background brightness:
  - Dark background → SemiBold (600)
  - Light background → Medium (500)
- White centred text with drop shadow
- Links stripped — images contain quote text only
- Post-generation review per image:
  - `1` Approve
  - `2` Regenerate with lighter overlay
  - `3` Regenerate with darker overlay
  - `4` Skip and delete

**Font:** Atkinson Hyperlegible Mono at 34px

---

### `pipeline.py` — One-Command Pipeline Runner

Runs the full pipeline — fetch → transcribe → caption → images — in a single command.

**Two modes:**

**Full Auto** — smart defaults, no interruptions after episode selection:
- Fetches everything
- Groq transcription, segment timestamps, fallback to offline
- Captions for all platforms, auto-saved with `_pending_review` suffix
- Images generated, review skipped

**Guided Auto** — configure once, run uninterrupted:
- Walks through every decision point upfront
- Pre-flight validation after configuration — auto-corrects invalid settings before run starts
- Prints confirmation summary before proceeding
- Pipeline runs without stopping after confirmation

**Safety features:**
- Episode validated against RSS feed before anything runs
- Duplicate detection per mode
- Pending review backlog warning — scans entire `output/` tree, grouped by episode
- All runs logged to `pipeline_run.log`
- Captions always saved as `_pending_review` — never silently treated as final
- Groq fallback flagged immediately at point of switch and again in summary + log with reason
- Cover art absence logged as a note — does not fail the fetch stage
- Caption platform partial success tracked and noted
- Critical failures (fetch, transcribe) trigger hard stop
- Non-critical failures (captions, images) logged and skipped

**Pipeline menu:**
```
========================================
     🎙️  PODCAST AGENT PIPELINE
========================================
  1. Full Auto    — smart defaults, no interruptions
  2. Guided Auto  — configure once, then run

  T.  Use saved template (My Podcast — groq / segments)
  R.  📋 Review pending captions (3 file(s) awaiting review)

  0.  Cancel
========================================
```

- `T` option only appears when `pipeline_config.json` exists — shows saved podcast and settings
- `R` option only appears when pending review files exist
- Review session lets you mark individual files or all files as reviewed
- Marking removes `_pending_review` suffix — file becomes the approved version
- Pending count refreshes after every run and review session
- Estimated run time displayed before each run based on most recent `pipeline_run.log` entry
- Windows toast notification sent on Full Auto completion via `plyer` — falls back to terminal bell
- Guided Auto offers to save configuration as a reusable `pipeline_config.json` template after confirming

---

### `cleanup.py` — Folder Cleaner

Standalone utility that clears all files from `input/` and `output/` without deleting the folder structure.

- Requires typing `yes` in full — prevents accidental deletion
- Reports every deleted item
- Prints total files and folders deleted

```bash
python cleanup.py
```

---

## 📁 Output Files Per Episode

```
output/V073 Christians Lack Empathy - S6E5/
├── transcripts/
│   ├── V073 Christians Lack Empathy - S6E5.txt
│   ├── V073 Christians Lack Empathy - S6E5_segments.txt
│   └── V073 Christians Lack Empathy - S6E5_words.txt
├── captions/
│   ├── V073_twitter_captions.txt                      ← interactive (approved)
│   ├── V073_twitter_captions_pending_review.txt       ← pipeline (auto-saved)
│   ├── V073_twitter_references.txt
│   ├── V073_facebook_captions.txt
│   └── V073_facebook_references.txt
└── images/
    ├── V073_cover.jpg
    ├── V073_twitter_quote1_square.jpg
    ├── V073_twitter_quote2_square.jpg
    ├── V073_twitter_quote3_square.jpg
    ├── V073_facebook_quote1_square.jpg
    └── V073_facebook_quote2_square.jpg
```

---

## 📅 Development Timeline

All development took place in a single session on **March 15, 2026**, conducted collaboratively via Claude (claude.ai).

| Phase | What was built |
|---|---|
| 1–2 | Project concept, scoping and architecture |
| 3 | Environment setup — Windows, Python, VS Code, folder structure |
| 4–5 | Initial `transcribe.py` and `fetch.py` builds |
| 6 | `utils.py` created — shared time formatter |
| 7–9 | `transcribe.py` updated, `caption.py` and `imagegen.py` initial builds |
| 10 | `main.py` initial build — interactive menu |
| 11 | Groq integration added to `transcribe.py` |
| 12 | `launch.py` built — setup checker and launcher |
| 13 | Category A features — output organisation, error handling, status dashboard |
| 14 | Timestamped transcription and caption reference lists |
| 15 | `README.md` and documentation |
| 16 | Full code comments pass across all scripts |
| 17 | Code audit — `utils.py` refactored, shared `load_metadata()` centralised |
| 18 | Category C — single caption regeneration, post-generation image review |
| 19 | Category D — new episode detection, library version checker |
| 20–22 | Project summary, pipeline strategy design, `cleanup.py` created |
| 23–25 | Pipeline refactoring across all core scripts, `pipeline.py` built |
| 26 | `run_all.py` renamed to `launch.py` |
| 27 | Medium priority pipeline features — Groq notification, backlog review menu, Guided Auto edge cases |
| 28 | `plyer` added to `launch.py` library checks |
| 29 | Low priority pipeline features — estimated run time, config template, completion notification |

---

## 🔮 Planned Updates

| Priority | Feature |
|---|---|
| Category B | Transcription resume from checkpoint — resume interrupted transcriptions without starting over |
| Planned | Auto-posting to WhatsApp broadcast list |
| Planned | Scheduled runs triggered by new RSS episodes |

---

## 📝 Notes

- RSS feeds are saved after the first run — no need to re-enter them
- Podcast name is fetched automatically from the RSS feed
- All scripts display execution time on completion
- Whisper runs fully offline after the initial model download
- Gemini and Groq both have free tiers sufficient for regular podcast use
- Every episode gets its own subfolder — outputs never mix between episodes
- Captions generated via pipeline are always marked `_pending_review` — review before posting
- All pipeline runs are logged to `pipeline_run.log`