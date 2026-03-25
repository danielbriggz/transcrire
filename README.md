# 🎙️ Transcrire

> A semi-automated content pipeline that transforms podcast episodes into platform-ready social media assets — captions, quote cards and timestamp reference lists — with minimal manual effort.

---

## 👤 Developer

**Daniel "Briggz" Adisa**

| Platform | Link |
|---|---|
| Instagram | https://instagram.com/danielbriggz |
| LinkedIn | https://linkedin.com/in/danieladisa |
| Twitter/X | https://x.com/danielBriggz |
| GitHub | https://github.com/danielbriggz/transcrire |

---

## 📌 Overview

Transcrire is a Python-based CLI tool built for solo podcasters who want to repurpose episode content for social media without spending hours on manual editing and formatting.

Given a podcast episode, Transcrire can:

1. **Fetch** the episode audio, cover art and Spotify link directly from your RSS feed
2. **Transcribe** the audio — locally via Whisper or via the cloud using Groq
3. **Generate** platform-specific social media captions using Google Gemini
4. **Create** styled quote card images using the episode cover art as a background

It also supports transcribing any audio file directly from your computer — no RSS feed required.

**Built entirely with free tools and APIs.** Designed for Windows, with practical constraints in mind.

---

## 💾 Installation

### Option 1 — `Transcrire.cmd` (Recommended for most users)

No VS Code, no Git, no manual setup. Just double-click and go.

1. Download `Transcrire.cmd`
2. Double-click it
3. Follow the on-screen prompts — Python check, dependency install, API key setup
4. Transcrire launches automatically

On first run the installer:
- Checks Python is installed (warns if 3.13+)
- Downloads the project from GitHub automatically
- Creates a virtual environment in `%APPDATA%\Transcrire\`
- Installs all dependencies
- Prompts for your Gemini and Groq API keys
- Creates your working folders on the Desktop

On every subsequent run it launches directly — skipping setup.

**File locations:**
- Scripts and config → `%APPDATA%\Transcrire\` (hidden from user)
- Input and output folders → `Desktop\Transcrire\` (user-facing)

---

### Option 2 — Manual Setup (Developers / VS Code)

**Requirements:**
- Python 3.10–3.12 *(3.13 has known audio library issues)*
- VS Code (recommended)
- ffmpeg installed and added to system PATH

**Install dependencies:**
```bash
pip install openai-whisper feedparser requests google-genai groq pillow plyer python-dotenv
```

**API Keys:**

Create a `.env` file in the project root:
```
GEMINI_API_KEY=your-gemini-api-key-here
GROQ_API_KEY=your-groq-api-key-here
```

| Key | Free tier at |
|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| `GROQ_API_KEY` | https://console.groq.com |

`launch.py` will prompt for and validate both keys automatically on first run and save them to `.env`.

---

## 🗂️ Project Structure

```
transcrire/
│
├── input/                            # Downloaded audio files
│
├── output/
│   └── {Episode Title} - SxEx/       # Per-episode subfolder (auto-created)
│       ├── transcripts/               # Plain or timestamped transcripts
│       ├── captions/                  # Captions + reference lists
│       └── images/                    # Cover art + quote card images
│   ├── pc_transcripts/                # Transcripts from PC audio uploads
│   ├── chunks/                        # Temporary audio chunks (auto-cleared)
│   ├── metadata.json                  # Active episode info
│   └── new_episodes.json              # Unprocessed RSS episodes (auto-generated)
│
├── assets/
│   └── fonts/                         # Atkinson Hyperlegible Mono weights
│
├── scripts/
│   ├── fetch.py                       # RSS feed fetcher
│   ├── transcribe.py                  # Audio transcriber
│   ├── caption.py                     # Caption generator
│   ├── imagegen.py                    # Quote card generator
│   ├── chunker.py                     # Audio chunker + checkpoint manager
│   └── utils.py                       # Shared utilities
│
├── .env                               # API keys (never committed to GitHub)
├── .env.example                       # API key template for new users
├── .gitignore                         # Excludes keys, state files, venv
├── feeds.json                         # Saved RSS feeds
├── history.json                       # Episode processing history
├── setup.json                         # First-time setup flag
├── pipeline_run.log                   # Automated pipeline run log
├── pipeline_config.json               # Saved Guided Auto configuration template
├── launch.py                          # Setup checker + interactive launcher
├── main.py                            # Interactive main menu
├── pipeline.py                        # Full one-command pipeline runner
├── cleanup.py                         # Input/output folder cleaner
├── config.py                          # Folder paths + .env key loading
└── Transcrire.cmd                     # Windows installer + launcher
```

---

## 🚀 Entry Points

| Command | What it does |
|---|---|
| Double-click `Transcrire.cmd` | Install or launch Transcrire (no terminal needed) |
| `python launch.py` | Run setup checks + launch interactive menu |
| `python launch.py --setup` | Force re-run all setup checks |
| `python pipeline.py` | Launch pipeline with mode selection |
| `python pipeline.py --auto --season 6 --episode 5` | Full Auto — prompts for podcast only |
| `python pipeline.py --auto --season 6 --episode 5 --podcast "My Podcast"` | Fully non-interactive |
| `python pipeline.py --config --season 6 --episode 5` | Load saved config template |
| `python pipeline.py --review` | List all pending review caption files |
| `python cleanup.py` | Delete all files in `input/`, `output/` and state files |

---

## 🛠️ Features

### `Transcrire.cmd` — Windows Installer & Launcher

The primary entry point for non-developer users. No Git, no VS Code, no terminal knowledge required.

**First-time installation:**
- Python version check with 3.13+ warning
- Project downloaded from GitHub as a `.zip` via `curl` (built into Windows 10/11)
- Virtual environment created in `%APPDATA%\Transcrire\`
- All Python dependencies installed automatically
- Gemini and Groq API keys collected and saved to `.env`
- Desktop working folders created

**Every launch:**
- Detects existing install — skips setup
- Checks `.env` for missing keys — prompts only for the one that's missing
- Sets environment variables so scripts resolve correct paths
- Launches `launch.py`

---

### `launch.py` — Setup Checker

Runs on first launch, skipped on subsequent runs unless `--setup` is passed.

- Python version check — warns if 3.13+, opens download page if user declines
- Missing library detection — offers mass install
- Library version check — compares installed vs latest PyPI versions, offers one-command update
- ffmpeg check — step-by-step installation guidance if missing
- API key validation — live test call before saving to `.env`
- Missing key prompt — if a key is absent, prompts inline and saves without restarting
- Font auto-download — all 7 Atkinson Hyperlegible Mono weights
- Output folder creation
- New episode detection — silently checks RSS feed on every launch, notifies in main menu

---

### `main.py` — Interactive Menu

The menu starts with audio source selection before showing pipeline options.

**Source selection (entry point):**
```
========================================
        🎙️  TRANSCRIRE
========================================
  Select audio source:

  1. 💻  Upload from PC      (transcription only)
  2. 📡  Podcast RSS         (full pipeline)
----------------------------------------
  0.     Exit
========================================
```

**PC Upload path:**
- Transcription only — no fetch, captions or images
- Point to any audio file on your computer
- Choose transcription mode (Groq or offline) and transcript type
- After transcription, optionally copy the transcript to any folder

**RSS path:**
```
========================================
        🎙️  TRANSCRIRE — RSS
========================================
  📻 S6E5 — V073 Christians Lack Empa...
----------------------------------------
  1. ✅ Fetch Episode
  2. ✅ Transcribe
  3. ✅ Create Captions
  4. ⬜ Generate Images
----------------------------------------
  0.    Back to source selection
========================================

  🆕  1 new episode(s) available:
     1. S6E6 — V074 | The Problem With...

  N.  Fetch a new episode from the list above
```

- Status indicators (✅ / ⬜) per pipeline step — refreshes on every return
- New episode notification banner for unprocessed RSS episodes
- `N` shortcut to jump directly to fetching a new episode
- `0` returns to source selection

---

### `fetch.py` — Episode Fetcher

- Saves RSS feeds persistently in `feeds.json` — podcast name fetched automatically
- Always shows full saved feed list with option to add a new RSS feed
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

- Choose audio from the `input/` folder or paste any full file path from your computer
- Validates file exists and is a supported format before proceeding
- Transcript type prompt available for both RSS and PC upload paths
- Groq mode compresses audio via ffmpeg before upload — auto-fallback to Whisper if file exceeds 25MB
- **Checkpoint-aware transcription** for files over 5 minutes:
  - Audio split into 5-minute chunks via ffmpeg
  - Progress saved after every chunk to `output/transcription_checkpoint.json`
  - If interrupted, resumes from last completed chunk on next run
  - Stale checkpoints from a different job prompt user before discarding
  - Chunks deleted automatically on successful completion
  - Timestamps accurately offset per chunk — final transcript is always correct
- RSS transcripts saved to per-episode subfolder
- PC upload transcripts saved to `output/pc_transcripts/`

---

### `scripts/chunker.py` — Audio Chunker & Checkpoint Manager

Handles all chunking and checkpoint logic for long transcriptions.

- Splits audio into 5-minute segments via ffmpeg
- Saves transcription state after every chunk to `output/transcription_checkpoint.json`
- Detects and resumes from a matching checkpoint on restart
- Handles stale checkpoints — prompts user to delete, keep or cancel
- Stitches chunk transcripts with timestamp offsetting for segment and word-level types
- Clears checkpoint and chunk files on successful completion

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
- Four actions per platform: Approve / Regenerate all / Skip / Edit individual caption
- Single caption regeneration — Gemini replaces only the selected caption in matching style
- Generates a `_references.txt` file per platform when a timestamped transcript is used

---

### `imagegen.py` — Quote Card Generator

- Generates square (1080×1080) images — 3 Twitter + 2 Facebook per episode
- Episode cover art as background: blurred + dark overlay
- Auto font weight selection based on background brightness:
  - Dark background → SemiBold
  - Light background → Medium
- White centred text with drop shadow
- Links stripped — images contain quote text only
- Post-generation review per image: Approve / Lighter overlay / Darker overlay / Skip and delete

**Font:** Atkinson Hyperlegible Mono at 34px

---

### `pipeline.py` — One-Command Pipeline Runner

Runs the full pipeline — fetch → transcribe → caption → images — in a single command.

**Audio source selection:**
```
Select audio source:
  1. 💻  Upload from PC      (transcription only)
  2. 📡  Podcast RSS         (full pipeline)
  0.     Cancel
```

**Pipeline menu (RSS):**
```
========================================
     🎙️  TRANSCRIRE PIPELINE
========================================
  1. Full Auto    — smart defaults, no interruptions
  2. Guided Auto  — configure once, then run

  T.  Use saved template (My Podcast — groq / segments)
  R.  📋 Review pending captions (3 file(s) awaiting review)

  0.  Cancel
========================================
```

**Full Auto** — smart defaults, no interruptions after episode selection.

**Guided Auto** — configure every decision once upfront, run uninterrupted. Includes pre-flight validation, save-as-template option and confirmation summary.

**Safety features:**
- Episode validated against RSS feed before anything runs
- Duplicate detection per mode
- Pending review backlog warning — scans entire `output/` tree, grouped by episode
- All runs logged to `pipeline_run.log`
- Captions always saved as `_pending_review` — never silently treated as final
- Groq fallback flagged immediately at point of switch and again in summary + log
- Critical failures (fetch, transcribe) trigger hard stop
- Non-critical failures (captions, images) logged and skipped

**Other pipeline features:**
- `T` option — loads saved `pipeline_config.json` template (only shown when it exists)
- `R` option — review pending captions inline (only shown when files exist)
- Estimated run time shown before each run based on previous log entry
- Windows toast notification on Full Auto completion via `plyer`
- Post-run backlog count displayed with `--review` flag hint

---

### `cleanup.py` — Folder Cleaner

Standalone utility that clears all files from `input/`, `output/` and runtime state files.

- Requires typing `yes` in full — prevents accidental deletion
- Clears: `input/`, `output/`, `history.json`, `metadata.json`, `new_episodes.json`, `transcription_checkpoint.json`
- Reports every deleted item with total count

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

PC upload transcripts are saved to:
```
output/pc_transcripts/
└── The Samson Essay_segments.txt
```

---

## 🧰 Frameworks & Libraries

### Core Language

| Tool | Role |
|---|---|
| Python 3.10–3.12 | Primary language |

### AI & Transcription

| Library | Role |
|---|---|
| `openai-whisper` | Offline audio transcription — small model |
| `groq` | Fast cloud transcription via Whisper Large v3 API |
| `google-genai` | Caption generation via Gemini 2.5 Flash |

### Audio Processing

| Tool | Role |
|---|---|
| `ffmpeg` | Audio compression before Groq upload, chunk splitting |
| `ffprobe` | Audio duration detection for chunking decision |

### Data & Networking

| Library | Role |
|---|---|
| `feedparser` | RSS feed parsing |
| `requests` | HTTP requests for cover art and font downloads |
| `python-dotenv` | `.env` file loading for API key management |

### Image Generation

| Library | Role |
|---|---|
| `Pillow` | Quote card image creation, cover art processing |

### Notifications

| Library | Role |
|---|---|
| `plyer` | Windows toast notifications on pipeline completion |

### Distribution

| Tool | Role |
|---|---|
| `Transcrire.cmd` | Windows installer and launcher — no Git required |
| `curl` | Built into Windows 10/11 — downloads project zip from GitHub |
| GitHub | Source of truth for distribution — all installs pull from here |

### Typography

| Asset | Role |
|---|---|
| Atkinson Hyperlegible Mono | Quote card font — 7 weights, downloaded from Google Fonts |

---

## 📅 Development Timeline

Development conducted collaboratively via Claude (claude.ai).

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
| 30 | Custom audio file path added to `transcribe.py` |
| 31 | Menu revamp — audio source selection, PC upload path, RSS pipeline path |
| 32 | PC upload fixes — dedicated save folder, temp prefix stripped, transcript type prompt |
| 33 | Program renamed to Transcrire — pitch deck created |
| 34 | Transcription checkpoint — chunked transcription with resume-on-failure |
| 35 | Bug fix — duplicate check running unconditionally in pipeline |
| 36 | Bug fix — pipeline RSS selection always auto-selected first feed |
| 37 | `cleanup.py` updated — state files added, Transcrire rename |
| 38 | GitHub repository setup — `.gitignore`, `.env`, `.env.example` |
| 39 | `Transcrire.cmd` built — Windows installer and launcher |
| 40 | Distribution fixes — `.env` path resolution, PC transcript folder, inline key prompt |
| 41 | Test run confirmed — installer, pipeline, PC upload and checkpoint all working |

---

## 🔮 Planned Updates

| Feature | Notes |
|---|---|
| GUI interface | Flask/FastAPI backend + React frontend — planned as next major phase |
| Auto-posting to WhatsApp | Requires WhatsApp Business API — deferred pending free tier availability |
| Scheduled RSS runs | Automatic pipeline trigger when new episode detected |

---

## 📝 Notes

- RSS feeds are saved after the first run — no need to re-enter them
- Podcast name is fetched automatically from the RSS feed
- All scripts display execution time on completion
- Whisper runs fully offline after the initial model download (~244MB, one-time)
- Gemini and Groq both have free tiers sufficient for regular podcast use
- Every episode gets its own subfolder — outputs never mix between episodes
- Captions generated via pipeline are always marked `_pending_review` — review before posting
- All pipeline runs are logged to `pipeline_run.log`
- API keys are stored in `.env` and never committed to GitHub
- When launched via `Transcrire.cmd`, all user files are saved to `Desktop\Transcrire\`