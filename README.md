# Transcrire

> A podcast content pipeline that automates the repurposing of episode audio into social media assets.

**Status:** Active rebuild — ground-up rewrite targeting Python 3.12.  
**Repository:** [github.com/danielbriggz/transcrire](https://github.com/danielbriggz/transcrire)  
**Developer:** Daniel "Briggz" Adisa

---

## What Is Transcrire?

Transcrire is a CLI tool built for solo podcasters who want to repurpose episode content for social media without spending hours doing it manually.

Given a podcast episode, Transcrire fetches the audio and metadata, transcribes it, generates platform-specific social media captions, and produces styled quote card images — all from a single pipeline.

This repository is a **ground-up rebuild** of the original codebase, motivated by accumulated technical debt. The rebuild targets a cleaner architecture, a better developer experience, and a foundation solid enough to support the full feature set going forward.

---

## What Does It Do?

Transcrire processes a podcast episode through four stages:

```
Fetch → Transcribe → Caption → Image Generation
```

| Stage | Description |
|---|---|
| **Fetch** | Retrieves episode audio, cover art and episode link from an RSS feed |
| **Transcribe** | Converts audio to text via Groq (cloud) or Whisper (local) |
| **Caption** | Generates platform-specific social media captions via Gemini |
| **Image Generation** | Produces styled quote card images using the episode cover art |

---

## Key Features

- **Dual transcription modes** — fast cloud transcription via Groq, or fully offline via Whisper
- **Timestamped transcripts** — plain, segment-level, or word-level output
- **Multi-platform captions** — Twitter, LinkedIn, and Facebook, each with appropriate tone and format
- **Quote card generation** — blurred cover art backgrounds, auto font weight selection, 1080×1080 output
- **State-aware TUI** — guided menu driven by what has and hasn't been completed for the active episode
- **SQLite-backed state management** — derived episode state, no stale status columns
- **Hybrid DB + manifest sidecar model** — episode outputs are portable without losing context
- **Checkpoint-aware transcription** — chunked processing with resume-on-failure for long audio files
- **Lazy API validation** — credentials are checked when first needed, not on startup
- **Exponential backoff** — all external API calls use `tenacity`-based retry logic
- **Automated pipeline mode** — run the full sequence unattended with smart defaults or upfront configuration

---

## System Requirements

| Requirement | Detail |
|---|---|
| **Python** | 3.12 (required) |
| **OS** | Windows (primary target) |
| **Package manager** | [`uv`](https://docs.astral.sh/uv/) |
| **ffmpeg** | Required for audio processing — must be on system PATH |
| **Internet** | Required for Groq and Gemini API calls (offline transcription available via Whisper) |

### API Keys

Two free API keys are required:

| Key | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |

Create a `.env` file in the project root using `.env.example` as a template.

---

## Installation

```bash
# Clone the repository
git clone https://github.com/danielbriggz/transcrire.git
cd transcrire

# Switch to the rebuild branch
git checkout rebuild

# Install dependencies
uv sync

# Copy the environment template and fill in your API keys
cp .env.example .env
```

> **ffmpeg** must be installed separately and accessible on your system PATH.  
> Windows users: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add `C:\ffmpeg\bin` to PATH.

---

## Project Structure

```
transcrire/
├── transcrire/              # Main package
│   ├── config.py            # Unified configuration via pydantic-settings
│   ├── logger.py            # Structured logging
│   ├── events.py            # Internal event emitter
│   ├── domain/              # Core domain layer
│   │   ├── enums.py         # Pipeline stage and status enums
│   │   ├── episode.py       # Episode model
│   │   └── stage_result.py  # Stage outcome model
│   └── storage/
│       └── db.py            # SQLite state management
├── .env.example             # API key template
├── pyproject.toml           # Project metadata and dependencies
└── README.md
```

---

## Planned Development

The rebuild is working toward feature parity with the original codebase, then beyond it.

**In scope for this rebuild:**

- Full pipeline implementation — fetch, transcribe, caption, image generation
- State-aware TUI menu driven by `pipeline.get_available_actions()`
- Idempotency contracts across all pipeline stages
- Groq + Whisper transcription with checkpoint resume
- Gemini-powered caption generation with preview and approval flow
- Quote card image generation from episode cover art
- Automated pipeline mode — Full Auto and Guided Auto

**Deferred to post-rebuild:**

- Queue-based architecture for batch episode processing
- Output versioning
- WebSocket support
- GUI interface

---

## Notes

- The `main` branch is preserved and tagged `v1.0-legacy` — it contains the original, fully-featured codebase
- The `rebuild` branch is the active development branch
- API keys are stored in `.env` and are never committed to the repository
- `uv` is the only supported package manager for this rebuild