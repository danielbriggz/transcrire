# Transcrire — Architecture Proposal & Feature Audit

### Rebuild Edition

> Written before a single line of code is written. Every architectural decision is made here, not during development.
>
> **Labels used throughout:**
>
> - `[REBUILD]` — included in the CLI rebuild
> - `[POST-REBUILD]` — planned for the GUI phase or later
> - `[CUT]` — removed entirely from the new build

---

## 1. Guiding Principles

These govern every decision in this document.

1. **State lives in a database, not the filesystem.** No more inferring "step complete" from whether a file exists.
2. **Business logic is framework-agnostic.** The CLI uses it. The future GUI uses the same thing. Nothing gets rewritten when the interface changes.
3. **Errors are handled in code, not delegated to the user.** "Wait and try again" is not error handling.
4. **Validate lazily.** API keys, ffmpeg, fonts — checked on first use, not on every launch.
5. **One config system.** No scattered constants, no `config.py` + `.env` split with unclear authority.
6. **Testable by design.** Pure functions in `core/` take inputs and return outputs. No hidden I/O.

---

## 2. Technology Decisions

| Concern             | Choice                            | Reason                                                                                           |
| ------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------ |
| Language            | Python 3.12                       | All key libraries are Python-native; switching languages means replacing the entire stack        |
| Package manager     | `uv`                              | Faster than pip, proper dependency locking, portable environments                                |
| State / database    | SQLite via `sqlite3` (stdlib)     | No infrastructure to run; sufficient for single-user local tool; solves ghost dependency problem |
| Config / env        | `pydantic-settings`               | Single source of truth; type-safe; reads `.env` automatically; validates on load                 |
| Logging             | Python `logging` + JSON formatter | Structured, machine-readable, debuggable in the field                                            |
| API retries         | `tenacity`                        | Declarative exponential backoff; removes retry logic from business code                          |
| HTTP                | `httpx`                           | Modern, cleaner than `requests`; async-ready for GUI phase                                       |
| CLI framework       | `typer`                           | Clean, type-annotated CLI; auto-generates help text; easy to extend                              |
| Testing             | `pytest`                          | Standard; works cleanly with `uv`                                                                |
| Image generation    | `Pillow`                          | Carries over; no better free alternative                                                         |
| Audio transcription | `openai-whisper` + `groq`         | Carries over                                                                                     |
| Caption generation  | `google-genai`                    | Carries over                                                                                     |
| RSS parsing         | `feedparser`                      | Carries over                                                                                     |
| Notifications       | `plyer`                           | Carries over; lazy-imported so absence doesn't crash                                             |

**Dropped:**

- Raw `pip` + `venv` → replaced by `uv`
- `requests` → replaced by `httpx`
- `argparse` → replaced by `typer`
- Manual `.env` parsing in `launch.py` → replaced by `pydantic-settings`
- `subprocess` for ffmpeg calls → wrapped cleanly in `services/audio.py`

---

## 3. Project Structure

```
transcrire/
│
├── pyproject.toml              ← uv project definition, all dependencies
├── .env                        ← API keys (never committed)
├── .env.example                ← template
├── .gitignore
│
├── transcrire/                 ← main package
│   │
│   ├── core/                   ← pure business logic — no I/O, fully testable
│   │   ├── pipeline.py         ← pipeline orchestration (state transitions)
│   │   ├── captions.py         ← caption prompt building, parsing
│   │   ├── images.py           ← image composition logic
│   │   └── transcript.py       ← transcript formatting, stitching, offsetting
│   │
│   ├── services/               ← external API calls — all side effects isolated here
│   │   ├── groq.py             ← Groq transcription
│   │   ├── whisper.py          ← local Whisper transcription
│   │   ├── gemini.py           ← Gemini caption generation
│   │   ├── rss.py              ← feedparser wrapper
│   │   └── audio.py            ← ffmpeg/ffprobe wrappers
│   │
│   ├── storage/                ← all filesystem + database operations
│   │   ├── db.py               ← SQLite schema, queries, migrations
│   │   ├── episodes.py         ← episode folder creation, file saving
│   │   └── assets.py           ← fonts, cover art, audio file management
│   │
│   ├── cli/                    ← typer CLI — thin layer only, no logic here
│   │   ├── main.py             ← entry point, source selection menu
│   │   ├── rss.py              ← RSS pipeline commands
│   │   └── pc.py               ← PC upload commands
│   │
│   ├── config.py               ← pydantic-settings config, single source of truth
│   └── logger.py               ← structured JSON logging setup
│
├── tests/
│   ├── core/                   ← unit tests for pure functions
│   ├── services/               ← integration tests (can be skipped in CI)
│   └── storage/                ← database and filesystem tests
│
└── assets/
    └── fonts/                  ← Atkinson Hyperlegible Mono weights
```

**The rule:** if a function touches a file, a database, or an API, it lives in `services/` or `storage/`. If it only transforms data, it lives in `core/`. The `cli/` layer calls `core/` and `services/` — never directly manipulates files or state itself.

---

## 4. Configuration System `[REBUILD]`

**Old approach:** `config.py` with hardcoded fallbacks + manual `.env` parsing in `launch.py` + `os.environ` scattered everywhere.

**New approach:** Single `config.py` using `pydantic-settings`.

```python
# transcrire/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    gemini_api_key: str = ""
    groq_api_key: str = ""
    input_folder: str = "input"
    output_folder: str = "output"
    app_data_dir: str = ""  # set by Transcrire.cmd

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

- One import everywhere: `from transcrire.config import settings`
- Type-safe, validated on load
- `.env` location resolved cleanly via `env_file` — no manual path logic
- No hardcoded paths anywhere else in the codebase

**Debt eliminated:** scattered `os.getenv()` calls, `config.py` + `.env` split, `TRANSCRIRE_APPDATA` env var gymnastics in `launch.py`.

---

## 5. SQLite State Machine `[REBUILD]`

This is the single biggest structural upgrade in the rebuild.

### Schema

```sql
-- Episodes table: one row per processed episode
CREATE TABLE episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT NOT NULL,
    season          INTEGER NOT NULL,
    episode         INTEGER NOT NULL,
    title           TEXT,
    safe_title      TEXT,
    spotify_link    TEXT,
    folder_path     TEXT,          -- absolute path to episode folder
    state           TEXT NOT NULL DEFAULT 'CREATED',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(season, episode, podcast_name)
);

-- Stage results: one row per pipeline stage per episode
CREATE TABLE stage_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id),
    stage           TEXT NOT NULL,   -- FETCH, TRANSCRIBE, CAPTIONS, IMAGES
    status          TEXT NOT NULL,   -- COMPLETED, FAILED, SKIPPED
    output_paths    TEXT,            -- JSON array of output file paths
    error           TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL
);

-- Feeds table: replaces feeds.json
CREATE TABLE feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT NOT NULL UNIQUE,
    rss_url         TEXT NOT NULL,
    added_at        TEXT NOT NULL
);

-- Setup table: replaces setup.json, history.json
CREATE TABLE setup (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

### Episode State Machine

```
CREATED → FETCHED → TRANSCRIBED → CAPTIONS_GENERATED → IMAGES_GENERATED
                                                      ↘
                                                       COMPLETE
    (any state) → ERROR
```

**What this replaces:**

- `history.json` → `episodes` table
- `feeds.json` → `feeds` table
- `setup.json` → `setup` table
- `metadata.json` → `episodes` + `stage_results` tables
- `new_episodes.json` → query against `episodes` table
- Status dashboard file-existence checks → query episode state

**Debt eliminated:** ghost dependencies, folder-structure-as-state, stale `metadata.json` pointing to wrong episode, `new_episodes.json` cleanup logic.

---

## 6. Feature Audit — Full List with Debt & Rebuild Labels

---

### Launch & Setup

#### First-run setup check `[REBUILD]`

- **What it does:** Runs environment checks before main menu on first launch
- **Debt in old build:** Runs checks on every launch unless `setup.json` exists. `setup.json` is a flat file that doesn't track _what_ was checked, only _that_ setup ran. Individual checks (ffmpeg, fonts) not independently re-runnable.
- **Rebuild approach:** Setup state moves to `setup` table in SQLite. Each check (ffmpeg, fonts, api_keys) stored independently. Re-check any individual item without re-running everything.

#### Python version check `[REBUILD]`

- **What it does:** Warns if Python 3.13+ detected
- **Debt:** Opens a browser and exits — heavy-handed for a warning
- **Rebuild approach:** Warn clearly, continue unless explicitly blocked. `uv` pins Python version in `pyproject.toml` so this is largely a non-issue.

#### Library check `[CUT]`

- **What it does:** Detects missing pip packages, offers mass install
- **Why cut:** `uv` handles this entirely. Running `uv sync` installs everything from `pyproject.toml`. This check is redundant.

#### Library version checker `[CUT]`

- **What it does:** Compares installed vs PyPI versions, offers upgrade
- **Why cut:** `uv` manages this. `uv lock --upgrade` handles it properly. Manual PyPI polling in Python code is redundant and fragile.

#### ffmpeg check `[REBUILD]`

- **Debt:** Checked on every launch. Provides step-by-step Windows instructions inline which clutters the launch sequence.
- **Rebuild approach:** Checked once, stored in `setup` table. Only re-checked if a subsequent ffmpeg call fails. Instructions moved to `README` and a dedicated `--check` CLI flag.

#### API key validation `[REBUILD]`

- **Debt:** Live test call on every first-run setup. Wasteful and increases startup latency. As flagged in the external review.
- **Rebuild approach:** Lazy validation only. Keys stored in `.env` via `pydantic-settings`. First actual API call catches 401/403 and surfaces it cleanly. No startup test calls.

#### Font check + download `[REBUILD]`

- **Debt:** Checked on every launch via file existence. Download logic lives in `launch.py` — wrong layer.
- **Rebuild approach:** Font state in `setup` table. Download logic moves to `storage/assets.py`. Only triggered if a font file is missing when image generation actually runs.

#### Output folder creation `[REBUILD]`

- **Debt:** Hardcoded folder list in `launch.py`. Breaks if folder structure changes.
- **Rebuild approach:** Folders created on demand by `storage/episodes.py` when an episode is first created. No pre-creation needed.

#### New episode detection on launch `[REBUILD]`

- **Debt:** Saves results to `new_episodes.json`, requires cleanup logic, stale file possible.
- **Rebuild approach:** Query `episodes` table directly. No intermediate file.

---

### Main Menu / CLI

#### Audio source selection `[REBUILD]`

- **Debt:** Mixed into `main.py` with menu rendering and routing logic — three concerns in one function.
- **Rebuild approach:** `cli/main.py` handles routing only. Source selection is a `typer` command group.

#### RSS status dashboard `[REBUILD]`

- **Debt:** Status inferred from file existence — fragile. Long title truncation hardcoded at 28 chars.
- **Rebuild approach:** Status queried from `episodes` table. Truncation configurable.

#### New episode notification banner `[REBUILD]`

- **Debt:** Depends on `new_episodes.json` existing and being fresh.
- **Rebuild approach:** Live query against `feeds` table + `episodes` table on menu render.

#### PC upload path `[REBUILD]`

- **Debt:** Mixed into `main.py`. Transcript copy logic is UI concern bleeding into file logic.
- **Rebuild approach:** `cli/pc.py` handles PC upload commands. File copy logic moves to `storage/`.

#### Step continuation prompt `[REBUILD]`

- **Debt:** Hardcoded "continue to next step?" logic in `main.py` with a `NEXT` dict.
- **Rebuild approach:** Pipeline state in SQLite drives what's available next. CLI reads state and presents appropriate options.

---

### Episode Fetcher

#### RSS feed manager `[REBUILD]`

- **Debt:** `feeds.json` is a flat file. No metadata per feed (date added, last checked).
- **Rebuild approach:** `feeds` table in SQLite. `storage/db.py` handles all feed operations.

#### Episode search `[REBUILD]`

- **Debt:** Lives inside `fetch_episode()` — a monolithic function doing too many things.
- **Rebuild approach:** Isolated in `services/rss.py`. Returns a typed result object.

#### Selective fetch `[REBUILD]`

- **Debt:** Choice passed as a string (`"1"`, `"2"`, `"3"`, `"4"`) through the entire call stack.
- **Rebuild approach:** Typed enum: `FetchChoice.AUDIO | FetchChoice.COVER_ART | FetchChoice.LINK | FetchChoice.ALL`.

#### Duplicate detection `[REBUILD]`

- **Debt:** `check_duplicate()` in `fetch.py` takes a `config` param to change its behaviour — a function that works differently depending on who calls it is a design smell.
- **Rebuild approach:** Single function with explicit parameters. Pipeline passes `skip=True` explicitly. No behaviour switching via config dict.

#### Per-episode subfolder creation `[REBUILD]`

- **Debt:** Paths returned as a dict of strings. Any typo in a key silently returns `None`.
- **Rebuild approach:** Typed `EpisodePaths` dataclass. Attribute access, not string keys.

#### Metadata saving `[REBUILD]`

- **Debt:** `metadata.json` is a single active-episode file. Loading metadata from a previous session silently points at the wrong episode.
- **Rebuild approach:** Eliminated entirely. All metadata lives in `episodes` table.

#### History logging `[REBUILD]`

- **Debt:** `history.json` is a flat list with no indexing. Duplicate check iterates the whole list.
- **Rebuild approach:** `episodes` table with a UNIQUE constraint on `(season, episode, podcast_name)`. O(1) lookup.

#### Friendly error handling `[REBUILD]`

- **Debt:** Error messages are print statements scattered throughout `fetch.py`.
- **Rebuild approach:** Exceptions raised in `services/rss.py`, caught and formatted in `cli/rss.py`. Clean separation.

---

### Transcriber

#### Audio picker `[REBUILD]`

- **Debt:** Returns `(filename, folder)` tuple — easy to unpack in wrong order. Custom path strips quotes via a string replace — brittle.
- **Rebuild approach:** Returns a single `Path` object. `pathlib.Path` handles quote stripping and existence checks cleanly.

#### Dual transcription mode `[REBUILD]`

- **Debt:** Mode selected as `"1"` or `"2"` string, mapped internally. Easy to pass wrong value.
- **Rebuild approach:** `TranscribeMode` enum: `TranscribeMode.GROQ` / `TranscribeMode.WHISPER`.

#### Three transcript types `[REBUILD]`

- **Debt:** Type passed as string through the entire call stack. Type suffix logic duplicated in multiple places.
- **Rebuild approach:** `TranscriptType` enum. Suffix, filename, and formatting all derived from the enum in one place.

#### Groq audio compression `[REBUILD]`

- **Debt:** `subprocess.run` call inline in `transcribe_groq()`. ffmpeg arguments hardcoded.
- **Rebuild approach:** Isolated in `services/audio.py`. Returns compressed `Path` or raises typed exception.

#### Groq fallback to Whisper `[REBUILD]`

- **Debt:** Returns `(transcript, reason)` tuple on fallback — caller must check `isinstance(result, tuple)`. Fragile.
- **Rebuild approach:** Raises a typed `GroqFallbackError` exception. Caller catches it and routes to Whisper explicitly. No tuple duck-typing.

#### Exponential backoff `[REBUILD]`

- **Debt:** Rate limit errors print "wait and try again" to the user. No automatic retry.
- **Rebuild approach:** `tenacity` decorators on all API calls in `services/`. Exponential backoff with jitter, configurable max retries. User sees progress, not raw errors.

#### Checkpoint-aware chunked transcription `[REBUILD]`

- **Debt:** Checkpoint stored as JSON file. Chunk folder cleanup has multiple failure modes. `chunker.py` imports itself via `importlib.util` — a code smell indicating it shouldn't be a separate module.
- **Rebuild approach:** Checkpoint state moves to `setup` table (keyed by audio path hash). Chunking logic absorbed into `services/audio.py` and `core/transcript.py`. No separate `chunker.py`.

#### Timestamp stitching `[REBUILD]`

- **Debt:** Three separate `_offset_*` functions with similar logic. Regex-based timestamp parsing is fragile.
- **Rebuild approach:** Single `offset_timestamps(transcript, offset_seconds, type)` in `core/transcript.py`. Uses `datetime.timedelta` for arithmetic, not string manipulation.

#### PC vs RSS save routing `[REBUILD]`

- **Debt:** `if config.get("audio_source") == "pc"` branching inside `transcribe()`. The transcription function shouldn't know about audio sources.
- **Rebuild approach:** Caller determines save path before calling transcribe. Transcribe returns a transcript string. Caller saves it wherever appropriate.

#### Structured logging `[REBUILD]`

- **Debt:** `print()` statements everywhere. No log levels. No machine-readable output.
- **Rebuild approach:** `logger.py` sets up Python `logging` with a JSON formatter. Every module gets `logger = logging.getLogger(__name__)`. No `print()` in business logic.

---

### Caption Generator

#### Platform registry `[REBUILD]`

- **Debt:** Defined as a plain dict in `caption.py`. Instructions are multiline strings with `{link}` placeholders — easy to break with a formatting mistake.
- **Rebuild approach:** `Platform` dataclass with validated fields. Prompt building in `core/captions.py` as a pure function.

#### Transcript loader `[REBUILD]`

- **Debt:** File selection logic and transcript type preference logic mixed together. Falls back through a chain of `if` checks.
- **Rebuild approach:** Query `stage_results` table for transcript output paths. Type preference expressed as an ordered list, not a chain of conditionals.

#### Preview + approval loop `[REBUILD]`

- **Debt:** `while True` loop with string-matching on user input. Easy to get stuck.
- **Rebuild approach:** `typer` prompt with explicit choices. Loop logic simplified — approve returns, regenerate recurses cleanly.

#### Single caption regeneration `[REBUILD]`

- **Debt:** Parses caption numbers with regex. Splicing logic is fragile if Gemini returns unexpected formatting.
- **Rebuild approach:** Captions stored as a list internally throughout the generation flow. Index-based replacement, no regex parsing.

#### Reference list generation `[REBUILD]`

- **Debt:** Separate Gemini call with a different prompt — but called from inside the same function that handles approval. Two concerns mixed.
- **Rebuild approach:** Isolated in `core/captions.py` as `build_reference_prompt()`. Called explicitly after approval, not implicitly inside the approval loop.

#### Pipeline mode pending review `[REBUILD]`

- **Debt:** `_pending_review` suffix appended to filename. Reviewed by renaming the file. Fragile — any file manager rename breaks the suffix logic.
- **Rebuild approach:** `reviewed` boolean column in `stage_results` table. Filename stays clean. Review state lives in the database.

#### Hook detection prompt `[POST-REBUILD]`

- **What it would do:** Dedicated Gemini prompt to find high-engagement moments rather than just "notable segments"
- **Why post-rebuild:** Feature addition, not architectural fix. Design the prompt properly as a standalone feature.

#### Dynamic template / sentiment-based image layouts `[POST-REBUILD]`

- **What it would do:** Cycle through layout templates based on caption sentiment
- **Why post-rebuild:** Requires sentiment analysis pass and multiple image templates. Scope this separately after core image gen is stable.

---

### Image Generator

#### Cover art loader `[REBUILD]`

- **Debt:** Scans folder with string matching on filename suffixes. `max()` by mtime as fallback.
- **Rebuild approach:** Cover art path stored in `stage_results` after fetch. No folder scanning needed.

#### Caption loader `[REBUILD]`

- **Debt:** Prefers `_pending_review` files in pipeline mode — couples image gen to caption pipeline's naming convention.
- **Rebuild approach:** Caption paths stored in `stage_results`. Image gen reads from database, not from filesystem pattern matching.

#### Background brightness detection `[REBUILD]`

- **Debt:** Lives in `imagegen.py` — a UI/rendering concern mixed with image composition logic.
- **Rebuild approach:** Moves to `core/images.py` as a pure function. Takes image data, returns font weight enum.

#### Quote card generator `[REBUILD]`

- **Debt:** Monolithic function handling background, overlay, font, word wrap, shadow, and save in one block.
- **Rebuild approach:** Decomposed into composable steps in `core/images.py`: `build_background()`, `apply_overlay()`, `render_text()`, `save_image()`. Each independently testable.

#### Post-generation review `[REBUILD]`

- **Debt:** Review state tracked in a local list of dicts. Overlay opacity magic numbers (120, 160, 200) hardcoded inline.
- **Rebuild approach:** Review state in `stage_results`. Opacity values as named constants in `core/images.py`.

#### Waveform visualisation / live partial transcripts `[POST-REBUILD]`

- **Why post-rebuild:** GUI-phase features. Irrelevant for CLI.

#### Export formats (DOCX, SRT) `[POST-REBUILD]`

- **Why post-rebuild:** SRT maps directly to existing segment transcript format — low effort, but still a feature addition. Scope after core rebuild is stable.

---

### Pipeline Runner

#### Full Auto mode `[REBUILD]`

- **Debt:** `make_pipeline_config()` returns a plain dict. Key names are strings — typos silently pass `None` to downstream functions.
- **Rebuild approach:** `PipelineConfig` as a `pydantic` model. Validated on construction. Attribute access, not string keys.

#### Guided Auto mode `[REBUILD]`

- **Debt:** Long sequential input chain with no validation until the end. If the user makes a mistake early, they redo everything.
- **Rebuild approach:** `typer` prompts with inline validation. Each prompt validated immediately.

#### Pre-flight validation `[REBUILD]`

- **Debt:** Runs after Guided Auto confirmation — user answers all questions before being told Groq won't work.
- **Rebuild approach:** Connectivity and key checks run before the decision map, not after. User is informed of constraints upfront.

#### Config template `[REBUILD]`

- **Debt:** Saved to `pipeline_config.json`. Another flat file to track.
- **Rebuild approach:** Saved as a row in the `setup` table. Loaded by name.

#### Episode validator `[REBUILD]`

- **Debt:** Parses RSS feed again just to validate — redundant if the feed was just loaded for feed selection.
- **Rebuild approach:** Validation happens during `services/rss.py` fetch. Not a separate step.

#### Pending review backlog scanner `[REBUILD]`

- **Debt:** Scans filesystem for `_pending_review` suffix. Coupled to filename convention.
- **Rebuild approach:** Query `stage_results` WHERE `reviewed = FALSE AND stage = 'CAPTIONS'`.

#### `pipeline_run.log` `[REBUILD]`

- **Debt:** Append-only plain text file. Not machine-readable. Hard to parse for estimated run time.
- **Rebuild approach:** All run data in `stage_results` table. Structured JSON logging via `logger.py` for debugging. Estimated run time queried from `stage_results` directly.

#### Completion notification `[REBUILD]`

- **Debt:** `plyer` imported at top of `pipeline.py`. If not installed, import fails before the fallback logic runs.
- **Rebuild approach:** Lazy import inside the notification function. Falls back to terminal bell gracefully.

#### Queue-based decoupling / Kafka / RabbitMQ `[CUT]`

- **Why cut:** Appropriate for multi-tenant SaaS under concurrent load. We are a single-user local tool. The clean `core/` / `services/` separation already solves provider-swapping without queue infrastructure. Revisit if the product becomes multi-user.

#### Event-driven architecture / WebSockets / job IDs `[POST-REBUILD]`

- **Why post-rebuild:** Relevant for the GUI phase where the browser needs async progress updates. Not applicable to CLI.

---

### Chunker & Checkpoint Manager

#### Entire `chunker.py` module `[REBUILD — absorbed]`

- **Debt:** Imported via `importlib.util` in `transcribe.py` because both files are in `scripts/` — a workaround for a bad module structure. Checkpoint as JSON file.
- **Rebuild approach:** Split across `services/audio.py` (splitting) and `core/transcript.py` (stitching). Checkpoint state in `setup` table. `chunker.py` as a standalone module is eliminated.

---

### Shared Utilities

#### `format_time()` `[REBUILD]`

- **Debt:** Returns a formatted string — fine, but not consistent with Python's `timedelta`.
- **Rebuild approach:** Keep as a display utility in `cli/`. Core code uses `timedelta` internally.

#### `load_metadata()` `[CUT]`

- **Why cut:** `metadata.json` is eliminated. Replaced by database queries in `storage/db.py`.

#### `METADATA_PATH` constant `[CUT]`

- **Why cut:** No `metadata.json` in the rebuild.

---

### Cleanup Utility

#### Folder + state file cleanup `[REBUILD]`

- **Debt:** Deletes files and then separately deletes state files. Two separate loops for the same conceptual operation. `delete_folder_contents()` returns `None` when folder not found instead of `(0, 0)` — fixed in the old build but fragile.
- **Rebuild approach:** `transcrire clean` as a `typer` command. Database rows cleared alongside files. Single transaction — either everything clears or nothing does.

#### Confirmation gate `[REBUILD]`

- **Debt:** Requires typing `yes` — good idea, but implemented as a plain `input()` comparison.
- **Rebuild approach:** `typer.confirm()` with `--force` flag for scripted use.

---

### Windows Installer (`Transcrire.cmd`)

#### First-run installer `[REBUILD]`

- **Debt:** Batch script logic is hard to read and maintain. `curl` + PowerShell `Expand-Archive` combo is fragile on some Windows configurations. Writing `user_paths.py` to override config is a hack.
- **Rebuild approach:** `uv` handles environment creation and dependency installation in one command. Installer script simplified significantly — just: check Python, download, `uv sync`, set env vars, launch. `pydantic-settings` handles path overrides cleanly via env vars — no `user_paths.py` needed.

#### File separation (AppData vs Desktop) `[REBUILD]`

- **Debt:** `TRANSCRIRE_APPDATA`, `TRANSCRIRE_INPUT`, `TRANSCRIRE_OUTPUT` env vars set in `.cmd` and read in `config.py` — works but fragile if env vars aren't set.
- **Rebuild approach:** `pydantic-settings` reads these env vars with typed defaults. If not set, falls back to project root for development. Single config object, no scattered `os.environ.get()` calls.

---

## 7. Testing Strategy

The `core/` separation makes testing straightforward. All pure functions in `core/` are unit tested without mocking.

```
tests/
├── core/
│   ├── test_transcript.py      ← timestamp offsetting, stitching, formatting
│   ├── test_captions.py        ← prompt building, caption parsing
│   └── test_images.py          ← brightness detection, word wrap logic
├── services/
│   ├── test_rss.py             ← feed parsing (uses fixture XML)
│   └── test_audio.py           ← ffmpeg wrapper (requires ffmpeg installed)
└── storage/
    ├── test_db.py              ← SQLite schema, queries, state transitions
    └── test_episodes.py        ← folder creation, path resolution
```

**Services tests are marked `@pytest.mark.integration`** and skipped in fast CI runs. Core tests always run.

---

## 8. What's Explicitly Out of Scope for the Rebuild

These are not rejected permanently — they're deferred to avoid scope creep during the CLI rebuild.

| Feature                         | Status           | Notes                                                       |
| ------------------------------- | ---------------- | ----------------------------------------------------------- |
| GUI (Flask/FastAPI + React)     | `[POST-REBUILD]` | Same `core/` layer, new interface on top                    |
| WebSockets / async progress     | `[POST-REBUILD]` | GUI phase                                                   |
| Waveform visualisation          | `[POST-REBUILD]` | GUI phase                                                   |
| Live partial transcripts        | `[POST-REBUILD]` | GUI phase                                                   |
| SRT export                      | `[POST-REBUILD]` | Easy add after rebuild stabilises                           |
| DOCX export                     | `[POST-REBUILD]` | Same                                                        |
| Hook detection prompt           | `[POST-REBUILD]` | Prompt engineering task, not architecture                   |
| Dynamic image templates         | `[POST-REBUILD]` | Requires sentiment analysis pass                            |
| Multi-user / queue architecture | `[POST-REBUILD]` | Only relevant if product goes multi-tenant                  |
| Auto-posting to WhatsApp        | `[POST-REBUILD]` | API availability pending                                    |
| Scheduled RSS runs              | `[POST-REBUILD]` | After GUI phase                                             |
| Mac/Linux support               | `[POST-REBUILD]` | Windows-only for rebuild; `pathlib` usage keeps it portable |

---

## 9. Build Order

Once this proposal is approved, the build sequence is:

1. **Project scaffolding** — `uv` init, `pyproject.toml`, folder structure, `config.py`, `logger.py`
2. **Database layer** — SQLite schema, `storage/db.py`, migrations
3. **Services layer** — `rss.py`, `audio.py`, `groq.py`, `whisper.py`, `gemini.py` (with `tenacity` backoff on all)
4. **Core layer** — `transcript.py`, `captions.py`, `images.py`, `pipeline.py`
5. **Storage layer** — `episodes.py`, `assets.py`
6. **CLI layer** — `main.py`, `rss.py`, `pc.py` using `typer`
7. **Installer** — updated `Transcrire.cmd`
8. **Tests** — written alongside each layer, not after

---

## 10. Open Questions

These need answers before or during the build — flagged here rather than silently assumed.

| #   | Question                                                                                                                            | Impact                                                                    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 1   | Should the SQLite database live in `%APPDATA%\Transcrire\` or alongside the output folder?                                          | Affects portability — if user moves output folder, is the DB still valid? |
| 2   | Should `uv` be a hard requirement, or should a `pip install -r requirements.txt` fallback exist for users who won't use the `.cmd`? | Affects developer onboarding friction                                     |
| 3   | Is `typer` the right CLI framework, or is a simpler hand-rolled menu preferred for the interactive feel of the current build?       | `typer` is more structured but less "chatty" than the current menu style  |
