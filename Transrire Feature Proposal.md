# Transcrire — Architecture Proposal & Feature Audit
### Rebuild Edition (v3 — Consolidated)

> Written before a single line of code is written. Every architectural decision is made here, not during development.
>
> This document incorporates decisions from the original proposal, resolved open questions, implementation directives from the project lead, and a reviewed external proposal (v2).
>
> **Labels used throughout:**
> - `[REBUILD]` — included in the CLI rebuild
> - `[POST-REBUILD]` — planned for the GUI phase or later
> - `[CUT]` — removed entirely from the new build

---

## 1. Guiding Principles

These govern every decision in this document.

1. **State is derived, not stored.** Episode state is computed from `stage_results` at query time. No `episodes.state` column. No two sources of truth.
2. **The database is authoritative. Files are outputs only.** The manifest sidecar exists for portability and disaster recovery — not for runtime decision-making.
3. **Stages are idempotent.** Any stage can be safely re-run. Same input produces the same output and does not create a duplicate.
4. **Partial success is valid.** A pipeline that completes fetch and transcription but fails at captions has produced usable output. The completion model reflects this explicitly.
5. **Business logic is framework-agnostic.** The CLI uses `core/` today. The future GUI uses the same `core/` layer without modification.
6. **Errors are handled in code, not delegated to the user.** Exponential backoff is a code responsibility. "Wait and try again" is not error handling.
7. **Validate at the right moment.** API keys and ffmpeg are validated at pipeline start. Fonts and notifications are validated lazily, at first use.
8. **One config system.** No scattered constants, no split authority between `config.py` and `.env`.
9. **Testable by design.** Pure functions in `core/` take inputs and return outputs. No hidden I/O.

---

## 2. Technology Decisions

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.12 | All key libraries are Python-native; switching languages means replacing the entire stack |
| Package manager | `uv` (bootstrapped silently) | Faster than pip, proper dependency locking, portable environments; bootstrapped by `Transcrire.cmd` without user involvement |
| State / database | SQLite via `sqlite3` (stdlib) | No infrastructure to run; sufficient for single-user local tool; solves ghost dependency and derived-state problems |
| Config / env | `pydantic-settings` | Single source of truth; type-safe; reads `.env` automatically; validates on load |
| Logging | Python `logging` + JSON formatter | Structured, machine-readable, debuggable in the field |
| API retries | `tenacity` | Declarative exponential backoff; removes retry logic from business code entirely |
| HTTP | `httpx` | Modern, cleaner than `requests`; async-ready for GUI phase |
| CLI framework | `typer` with guided conversational loop | Structured, type-annotated commands; entry point implemented as a state-aware wizard, not a static option list |
| Domain objects | Python dataclasses | `Episode`, `StageResult` as typed domain objects; no plain dicts in business logic |
| Internal events | Lightweight custom emitter | `emit("stage_started")` etc.; decouples pipeline from CLI and future GUI |
| Testing | `pytest` | Standard; works cleanly with `uv` |
| Image generation | `Pillow` | Carries over; no better free alternative |
| Audio transcription | `openai-whisper` + `groq` | Carries over |
| Caption generation | `google-genai` | Carries over |
| RSS parsing | `feedparser` | Carries over |
| Notifications | `plyer` | Carries over; lazy-imported so absence does not crash |

**Dropped from the old build:**
- Raw `pip` + `venv` → replaced by `uv`
- `requests` → replaced by `httpx`
- `argparse` → replaced by `typer`
- Manual `.env` parsing in `launch.py` → replaced by `pydantic-settings`
- `subprocess` inline in `transcribe.py` → wrapped in `services/audio.py`
- `chunker.py` as a standalone module → absorbed into `services/audio.py` and `core/transcript.py`
- `metadata.json` → replaced by database queries
- `history.json`, `feeds.json`, `setup.json`, `new_episodes.json` → replaced by SQLite tables
- `pipeline_run.log` (plain text) → replaced by `stage_results` table + structured JSON logging

---

## 3. Project Structure

```
transcrire/
│
├── pyproject.toml              ← uv project definition, all dependencies, Python version pin
├── uv.lock                     ← locked dependency graph (committed to source control)
├── .env                        ← API keys (never committed)
├── .env.example                ← template for new users
├── .gitignore
│
├── transcrire/                 ← main package
│   │
│   ├── core/                   ← pure business logic — no I/O, fully testable
│   │   ├── pipeline.py         ← pipeline orchestration, available actions, completion level
│   │   ├── captions.py         ← prompt building, caption parsing, reference list building
│   │   ├── images.py           ← image composition logic, brightness detection, word wrap
│   │   └── transcript.py       ← formatting, stitching, timestamp offsetting, chunk logic
│   │
│   ├── services/               ← external calls and side effects — isolated here
│   │   ├── groq.py             ← Groq transcription (tenacity backoff)
│   │   ├── whisper.py          ← local Whisper transcription + chunk-level checkpoint
│   │   ├── gemini.py           ← Gemini caption generation (tenacity backoff)
│   │   ├── rss.py              ← feedparser wrapper, episode validation
│   │   └── audio.py            ← ffmpeg/ffprobe wrappers, audio splitting
│   │
│   ├── storage/                ← all filesystem + database operations
│   │   ├── db.py               ← SQLite schema, queries, migrations, WAL config
│   │   ├── episodes.py         ← episode folder creation, manifest write, file saving
│   │   └── assets.py           ← fonts, cover art, audio file management
│   │
│   ├── domain/                 ← typed domain objects
│   │   ├── episode.py          ← Episode dataclass, next_stage(), completion_level()
│   │   ├── stage_result.py     ← StageResult dataclass
│   │   └── enums.py            ← TranscribeMode, TranscriptType, FetchChoice, Stage, Status
│   │
│   ├── events.py               ← lightweight internal event emitter
│   │
│   ├── cli/                    ← typer CLI — thin rendering layer only, no logic
│   │   ├── main.py             ← entry point, source selection, state-aware menu
│   │   ├── rss.py              ← RSS pipeline wizard
│   │   └── pc.py               ← PC upload wizard
│   │
│   ├── config.py               ← pydantic-settings, single source of truth
│   └── logger.py               ← structured JSON logging setup
│
├── tests/
│   ├── core/                   ← unit tests — no mocking required
│   ├── services/               ← integration tests (marked, skippable in CI)
│   └── storage/                ← database and filesystem tests
│
└── assets/
    └── fonts/                  ← Atkinson Hyperlegible Mono weights
```

**The rule:** if a function touches a file, a database, or an API, it lives in `services/` or `storage/`. If it only transforms data, it lives in `core/`. The `cli/` layer calls `core/` and `storage/` — it never decides logic, it only renders what `pipeline.get_available_actions()` returns.

---

## 4. Configuration System `[REBUILD]`

**Old approach:** `config.py` with hardcoded fallbacks, manual `.env` parsing in `launch.py`, `os.environ` scattered throughout, and `user_paths.py` written by `Transcrire.cmd` as a path override hack.

**New approach:** Single `config.py` using `pydantic-settings`. All path resolution is handled here.

```python
# transcrire/config.py
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    gemini_api_key: str = ""
    groq_api_key: str = ""
    app_data_dir: Path = Path.home() / "AppData/Roaming/Transcrire"
    input_folder: Path = Path.home() / "Desktop/Transcrire/input"
    output_folder: Path = Path.home() / "Desktop/Transcrire/output"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "TRANSCRIRE_"
    }

settings = Settings()
```

`Transcrire.cmd` sets `TRANSCRIRE_APP_DATA_DIR`, `TRANSCRIRE_INPUT_FOLDER`, and `TRANSCRIRE_OUTPUT_FOLDER` as environment variables before launching. `pydantic-settings` reads them automatically via the `TRANSCRIRE_` prefix. In development (VS Code), none of these are set and the defaults apply. No `user_paths.py`, no manual parsing, no fragile fallback chains.

**Debt eliminated:** scattered `os.getenv()` calls, split config authority, `TRANSCRIRE_APPDATA` gymnastics, `user_paths.py` override hack.

---

## 5. Database Design `[REBUILD]`

### Schema

```sql
PRAGMA journal_mode=WAL;  -- Enables concurrent reads during writes

-- Episodes: one row per episode, no state column
CREATE TABLE episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT NOT NULL,
    season          INTEGER NOT NULL,
    episode         INTEGER NOT NULL,
    title           TEXT,
    safe_title      TEXT,
    spotify_link    TEXT,
    folder_path     TEXT,           -- absolute path; updated if folder is moved via recover
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(season, episode, podcast_name)
);

-- Stage results: one row per pipeline stage execution
CREATE TABLE stage_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id),
    stage           TEXT NOT NULL,      -- FETCH, TRANSCRIBE, CAPTIONS, IMAGES
    status          TEXT NOT NULL,      -- COMPLETED, FAILED, SKIPPED
    output_paths    TEXT,               -- JSON array of absolute output file paths
    error           TEXT,               -- error message if status = FAILED
    duration_ms     INTEGER,
    reviewed        INTEGER DEFAULT 0,  -- 1 = reviewed by user; replaces _pending_review suffix
    -- Reserved for POST-REBUILD (present in schema, not populated in v1):
    version         INTEGER DEFAULT 1,  -- output versioning
    input_hash      TEXT,               -- idempotency check
    cost_usd        REAL,               -- API spend tracking
    tokens_used     INTEGER,            -- LLM token usage
    created_at      TEXT NOT NULL
);

-- Feeds: replaces feeds.json
CREATE TABLE feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT NOT NULL UNIQUE,
    rss_url         TEXT NOT NULL,
    added_at        TEXT NOT NULL
);

-- Setup: replaces setup.json; stores per-check state and saved pipeline configs
CREATE TABLE setup (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,      -- JSON for complex values
    updated_at      TEXT NOT NULL
);
```

The reserved columns (`version`, `input_hash`, `cost_usd`, `tokens_used`) are present in the schema from the start so that post-rebuild features do not require migrations. They are not written to or read from during the rebuild.

### Derived Episode State

The `episodes` table has no `state` column. Episode state is always derived at query time.

```python
# core/pipeline.py
def derive_state(stage_results: list[StageResult]) -> EpisodeState:
    if any(r.status == Status.FAILED for r in stage_results):
        return EpisodeState.ERROR
    stages_completed = {r.stage for r in stage_results if r.status == Status.COMPLETED}
    if Stage.IMAGES in stages_completed:
        return EpisodeState.IMAGES_GENERATED
    if Stage.CAPTIONS in stages_completed:
        return EpisodeState.CAPTIONS_GENERATED
    if Stage.TRANSCRIBE in stages_completed:
        return EpisodeState.TRANSCRIBED
    if Stage.FETCH in stages_completed:
        return EpisodeState.FETCHED
    return EpisodeState.CREATED
```

Storing state explicitly would require keeping it in sync with `stage_results`. Any bug in that sync logic produces contradictory data. Deriving it is always consistent with the actual record.

### Tiered Completion Model

```python
# core/pipeline.py — part of Episode domain object
def completion_level(self) -> CompletionLevel:
    state = self.derive_state()
    if state == EpisodeState.IMAGES_GENERATED:
        return CompletionLevel.FULL         # transcript + captions + images
    if state == EpisodeState.CAPTIONS_GENERATED:
        return CompletionLevel.ENHANCED     # transcript + captions
    if state == EpisodeState.TRANSCRIBED:
        return CompletionLevel.BASIC        # transcript only
    return CompletionLevel.INCOMPLETE
```

This replaces binary pass/fail. A run that completes transcription but fails at captions is `BASIC`, not `FAILED`. The state-aware menu surfaces appropriate next actions based on the completion level.

### What the database replaces

| Old file | Replaced by |
|---|---|
| `history.json` | `episodes` table |
| `feeds.json` | `feeds` table |
| `setup.json` | `setup` table |
| `metadata.json` | `episodes` + `stage_results` tables |
| `new_episodes.json` | Query against `episodes` + `feeds` tables |
| `pipeline_run.log` | `stage_results` table + structured JSON log |
| `pipeline_config.json` | Row in `setup` table keyed by config name |
| `transcription_checkpoint.json` | Row in `setup` table keyed by audio path hash |

---

## 6. Manifest Strategy `[REBUILD]`

### Database location
The primary SQLite database (`transcrire.db`) lives in `%APPDATA%\Transcrire\`. It is protected from accidental deletion by sitting outside the user-facing output folder.

### Manifest sidecar
After every successful stage completion, `storage/episodes.py` writes a `manifest.json` into the episode's output folder alongside the episode files.

```json
{
  "podcast_name": "My Podcast",
  "season": 6,
  "episode": 5,
  "title": "V073 Episode Title",
  "spotify_link": "https://...",
  "stages": {
    "FETCH": { "status": "COMPLETED", "output_paths": [...], "completed_at": "..." },
    "TRANSCRIBE": { "status": "COMPLETED", "output_paths": [...], "completed_at": "..." },
    "CAPTIONS": { "status": "COMPLETED", "output_paths": [...], "completed_at": "..." },
    "IMAGES": { "status": "COMPLETED", "output_paths": [...], "completed_at": "..." }
  }
}
```

### Tiebreaker rule
The database is always authoritative for the running application. The manifest is never consulted during normal operation. It exists solely to support the `transcrire recover` command, which reconstructs a database row from a manifest when the database has been lost or when the episode folder has been moved to a new machine.

```
transcrire recover --folder "C:\Users\...\Desktop\Transcrire\output\V073 - S6E5"
```

This reads `manifest.json` from the specified folder and reconstructs the corresponding `episodes` and `stage_results` rows in the local database. It does not re-run any pipeline stages.

**Debt eliminated:** ghost dependencies, folder-structure-as-state, stale `metadata.json` pointing to the wrong episode, broken status indicators when output folders are renamed or moved.

---

## 7. Internal Event System `[REBUILD]`

A lightweight internal event emitter decouples the pipeline from whatever is consuming it. The pipeline emits events. The CLI registers handlers and renders them. The future GUI registers different handlers and sends WebSocket messages — no pipeline code changes required.

```python
# transcrire/events.py
from collections import defaultdict
from typing import Callable

_listeners: dict[str, list[Callable]] = defaultdict(list)

def on(event: str, handler: Callable) -> None:
    _listeners[event].append(handler)

def emit(event: str, **data) -> None:
    for handler in _listeners[event]:
        handler(**data)
```

| Event | Payload |
|---|---|
| `stage_started` | `stage`, `episode_id` |
| `stage_completed` | `stage`, `episode_id`, `output_paths`, `duration_ms` |
| `stage_failed` | `stage`, `episode_id`, `error` |
| `groq_fallback` | `episode_id`, `reason` |
| `checkpoint_saved` | `episode_id`, `chunk_index`, `total_chunks` |
| `pipeline_complete` | `episode_id`, `completion_level` |

---

## 8. State-Aware Menu (Guided TUI) `[REBUILD]`

The CLI entry point is not a static option list. It is a persistent conversational loop whose available actions change based on the current episode's derived state. The CLI calls `pipeline.get_available_actions(episode_id)` and renders only what is valid — it contains no `if state == X` logic of its own.

| Episode State | Menu Presented |
|---|---|
| No active episode | `1. Start new episode (RSS)` / `2. Transcribe PC audio` |
| `FETCHED` | `1. Transcribe` / `2. Fetch a different episode` |
| `TRANSCRIBED` | `1. Generate Captions` / `2. Review Transcript` / `3. Re-transcribe` |
| `CAPTIONS_GENERATED` | `1. Generate Images` / `2. Review Captions` / `3. Re-generate Captions` |
| `IMAGES_GENERATED` | `1. Review Images` / `2. Start New Episode` |
| `COMPLETE` | `1. Start New Episode` / `2. View Episode Summary` |
| `ERROR` | `1. Resume from [last successful stage]` / `2. View Error Details` / `3. Start Fresh` |

All state-to-action mapping lives in `core/pipeline.py`. The CLI receives a list of `Action` objects and renders them. This is the implementation of the project lead's directed decision: the menu is a guided assistant, not a technical utility.

---

## 9. Validation Strategy `[REBUILD]`

| Item | When validated | Why |
|---|---|---|
| API keys (Gemini, Groq) | At pipeline start, before first stage | Catch bad keys before a long run begins, not mid-run |
| ffmpeg | At pipeline start | Required for audio stages; catch early |
| Fonts | Lazy — at first image generation call | Not needed until images are generated |
| `plyer` notifications | Lazy — at completion notification call | Optional; absence should never crash the pipeline |

API key validation at pipeline start is a format check only — not empty, not a placeholder string. It is not a live test call. A genuine 401/403 from Groq or Gemini mid-run is caught by `tenacity`, logged, and surfaced as a `stage_failed` event.

**Debt eliminated:** live test API calls on every launch, startup latency, ffmpeg checked on every launch regardless of prior setup state.

---

## 10. Idempotency Contract `[POST-REBUILD]`

The schema includes `version` and `input_hash` columns on `stage_results`, present but not populated in the rebuild. When implemented, the contract is: same input hash means skip the stage and return existing output paths; changed input hash means write a new versioned output (`transcript_v2.txt`) without overwriting `transcript_v1.txt`.

This is deferred because versioned outputs add meaningful file management complexity that is out of rebuild scope. In the rebuild, idempotency is handled simply: if a stage has a `COMPLETED` row in `stage_results`, the CLI offers the option to re-run it explicitly rather than running it automatically.

---

## 11. Resumability Model `[REBUILD]`

For fetch, captions, and images, stage-level resumability is sufficient. These stages are fast enough that a full restart is acceptable on failure.

Offline Whisper transcription of a 60–90 minute episode can take 20–40 minutes. Losing this to a crash and restarting from zero is an unacceptable cost to the user. Chunk-level checkpointing is therefore retained specifically for the `TRANSCRIBE` stage when using offline Whisper — and only for that stage. Groq transcription is fast enough that stage-level restart is acceptable.

The checkpoint is stored as a row in the `setup` table keyed by the audio file's path hash, replacing the old `transcription_checkpoint.json`. The chunking logic lives in `services/whisper.py`. The stitching logic lives in `core/transcript.py`. There is no standalone `chunker.py` module.

---

## 12. Error Handling & Retry Strategy `[REBUILD]`

All API calls in `services/` use `tenacity` decorators for automatic exponential backoff with jitter.

```python
# Example — services/groq.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(4)
)
def transcribe(audio_path: Path, transcript_type: TranscriptType) -> str:
    ...
```

On exhaustion of retries, a typed exception is raised. `core/pipeline.py` catches it, emits `stage_failed`, and records it in `stage_results`. The user is never asked to "wait and try again."

---

## 13. Windows Installer `[REBUILD]`

### Silent `uv` bootstrap
`Transcrire.cmd` checks for `uv.exe` in `%APPDATA%\Transcrire\bin\`. If absent, it downloads the standalone binary via `curl` (built into Windows 10/11). All subsequent dependency operations use `uv sync` against `pyproject.toml` and `uv.lock` for reproducible, locked installs. `pip` remains as a fallback for developers running outside the `.cmd` launcher.

### Launch sequence (every run)
1. Check for `uv.exe` — download if missing
2. Set `TRANSCRIRE_APP_DATA_DIR`, `TRANSCRIRE_INPUT_FOLDER`, `TRANSCRIRE_OUTPUT_FOLDER`
3. Check `.env` for missing keys — prompt only for what is absent
4. Activate venv, run `uv sync --quiet` (fast no-op if nothing changed)
5. Launch `python -m transcrire`

### File separation
Scripts, venv, database, config, and fonts live in `%APPDATA%\Transcrire\` and are hidden from the user. The `input/` and `output/` folders live in `Desktop\Transcrire\` and are the only things the user sees and interacts with.

**Debt eliminated:** `user_paths.py` override hack, manual `pip install` in batch script, fragile `PowerShell Expand-Archive` combo, split config authority.

---

## 14. Feature Audit

---

### Launch & Setup

#### First-run setup check `[REBUILD]`
- **Debt:** Runs all checks on every launch unless `setup.json` exists. `setup.json` does not track which individual checks passed.
- **Rebuild approach:** Each check stored independently in the `setup` table. Any check can be re-run in isolation via `transcrire --check [item]`.

#### Python version check `[REBUILD]`
- **Debt:** Opens a browser and exits — disproportionate for a warning.
- **Rebuild approach:** Warn at launch and continue. `pyproject.toml` pins `requires-python = ">=3.10,<3.13"` so `uv` enforces this at install time.

#### Library check `[CUT]`
- **Why cut:** `uv sync` handles this entirely and correctly. The check is redundant.

#### Library version checker `[CUT]`
- **Why cut:** `uv lock --upgrade` handles this. Manual PyPI polling in Python code is redundant.

#### ffmpeg check `[REBUILD]`
- **Debt:** Checked on every launch.
- **Rebuild approach:** Checked once at pipeline start via `shutil.which("ffmpeg")`. Not stored — the check costs nothing. Detailed install instructions moved to `README` and a dedicated `transcrire --check ffmpeg` command.

#### API key validation `[REBUILD]`
- **Debt:** Live test call on every first-run setup. Wasteful and increases startup latency.
- **Rebuild approach:** Lazy validation only. Format check at pipeline start. First real 401/403 caught by `tenacity` and surfaced via the event system.

#### Font check + download `[REBUILD]`
- **Debt:** Check and download logic live in `launch.py` — wrong layer.
- **Rebuild approach:** Font state in `setup` table. Download logic in `storage/assets.py`. Triggered lazily at first image generation call.

#### Output folder creation `[REBUILD]`
- **Debt:** Hardcoded folder list in `launch.py`. Breaks if structure changes.
- **Rebuild approach:** Folders created on demand by `storage/episodes.py` when an episode is first created. No pre-creation required.

#### New episode detection on launch `[REBUILD]`
- **Debt:** Writes `new_episodes.json`; requires cleanup logic; can go stale.
- **Rebuild approach:** Live query against `feeds` and `episodes` tables on menu render. No intermediate file.

---

### Main Menu / CLI

#### Audio source selection `[REBUILD]`
- **Debt:** Mixed into `main.py` with routing logic and menu rendering — three concerns in one function.
- **Rebuild approach:** `cli/main.py` routes only. Source selection is the entry point to the state-aware menu.

#### State-aware menu `[REBUILD]`
- **Debt:** Static option list. Status inferred from file existence.
- **Rebuild approach:** Available actions derived from `pipeline.get_available_actions(episode_id)`. Episode state derived from `stage_results`. CLI renders what it receives — no state logic in the CLI layer.

#### New episode notification banner `[REBUILD]`
- **Debt:** Depends on `new_episodes.json` being fresh and present.
- **Rebuild approach:** Live query on menu render. No intermediate file.

#### PC upload path `[REBUILD]`
- **Debt:** Mixed into `main.py`. File copy logic not clearly separated.
- **Rebuild approach:** `cli/pc.py` handles PC upload commands. File operations in `storage/`.

#### Step continuation prompt `[REBUILD]`
- **Debt:** Hardcoded `NEXT` dict in `main.py`.
- **Rebuild approach:** Eliminated. The state-aware menu handles this naturally — after a stage completes, the menu re-derives state and presents the appropriate next actions automatically.

---

### Episode Fetcher

#### RSS feed manager `[REBUILD]`
- **Debt:** `feeds.json` flat file. No per-feed metadata.
- **Rebuild approach:** `feeds` table. `storage/db.py` handles all feed operations.

#### Episode search `[REBUILD]`
- **Debt:** Inside `fetch_episode()` — a monolithic function doing too many things.
- **Rebuild approach:** Isolated in `services/rss.py`. Returns a typed result or raises `EpisodeNotFoundError`.

#### Selective fetch `[REBUILD]`
- **Debt:** Choice passed as a string (`"1"`, `"2"`, `"3"`, `"4"`) through the entire call stack.
- **Rebuild approach:** `FetchChoice` enum in `domain/enums.py`.

#### Duplicate detection `[REBUILD]`
- **Debt:** `check_duplicate()` changes behaviour based on the contents of a `config` dict — a function that works differently depending on who calls it is a design smell.
- **Rebuild approach:** UNIQUE constraint on `(season, episode, podcast_name)` in the database. A duplicate raises `IntegrityError`. The pipeline catches it and decides whether to skip or proceed based on explicit parameters, not implicit config inspection.

#### Per-episode subfolder creation `[REBUILD]`
- **Debt:** Returns a plain dict of path strings. Key typos silently return `None`.
- **Rebuild approach:** `EpisodePaths` dataclass with `Path` attributes. Attribute access, not string key lookups.

#### Metadata saving `[REBUILD]`
- **Debt:** `metadata.json` is a single active-episode file. Stale between sessions. Downstream scripts silently use wrong-episode data.
- **Rebuild approach:** Eliminated entirely. All metadata in the `episodes` table. Manifest written to episode folder as a sidecar after each completed stage.

#### History logging `[REBUILD]`
- **Debt:** `history.json` flat list. No indexing. Duplicate check iterates the whole list.
- **Rebuild approach:** `episodes` table with UNIQUE constraint. O(1) lookup via database index.

#### Friendly error handling `[REBUILD]`
- **Debt:** Print statements scattered through `fetch.py`.
- **Rebuild approach:** Typed exceptions raised in `services/rss.py`. Caught and formatted in `cli/rss.py`. Emitted as `stage_failed` events for logging.

---

### Transcriber

#### Audio picker `[REBUILD]`
- **Debt:** Returns `(filename, folder)` tuple — easy to unpack in the wrong order.
- **Rebuild approach:** Returns a single `Path` object. `pathlib.Path` handles all path operations cleanly.

#### Dual transcription mode `[REBUILD]`
- **Debt:** Mode selected as `"1"` or `"2"` string.
- **Rebuild approach:** `TranscribeMode` enum in `domain/enums.py`.

#### Three transcript types `[REBUILD]`
- **Debt:** Type passed as string through the call stack. Suffix logic duplicated in multiple places.
- **Rebuild approach:** `TranscriptType` enum. Suffix, filename, and formatting all derived from the enum in one place.

#### Groq audio compression `[REBUILD]`
- **Debt:** `subprocess.run` call inline in `transcribe_groq()`. ffmpeg arguments hardcoded.
- **Rebuild approach:** Isolated in `services/audio.py`. Returns a compressed `Path` or raises a typed exception.

#### Groq fallback to Whisper `[REBUILD]`
- **Debt:** Returns `(transcript, reason)` tuple on fallback. Caller must check `isinstance(result, tuple)`. Fragile.
- **Rebuild approach:** Raises `GroqFallbackError`. Caller catches it explicitly, routes to Whisper, and emits a `groq_fallback` event. No tuple duck-typing.

#### Exponential backoff `[REBUILD]`
- **Debt:** Rate limit errors print "wait and try again." No automatic retry.
- **Rebuild approach:** `tenacity` decorators on all API calls in `services/`. Transparent to the user.

#### Chunk-level checkpoint (Whisper only) `[REBUILD]`
- **Debt:** `chunker.py` imported via `importlib.util`. Checkpoint as JSON file. Module has no clear home in the project structure.
- **Rebuild approach:** Chunking in `services/audio.py`. Stitching and offsetting in `core/transcript.py`. Checkpoint state in the `setup` table keyed by audio path hash. No standalone `chunker.py`.

#### Timestamp stitching `[REBUILD]`
- **Debt:** Three separate `_offset_*` functions with overlapping logic. Regex-based timestamp parsing.
- **Rebuild approach:** Single `offset_timestamps()` in `core/transcript.py`. Uses `datetime.timedelta` for arithmetic — no string manipulation.

#### PC vs RSS save routing `[REBUILD]`
- **Debt:** `if config.get("audio_source") == "pc"` branching inside `transcribe()`. The transcription function knows about audio sources — it should not.
- **Rebuild approach:** `transcribe()` returns a transcript string. The caller determines the save path before calling it.

#### Structured logging `[REBUILD]`
- **Debt:** `print()` statements throughout. No log levels. No machine-readable output.
- **Rebuild approach:** `logger = logging.getLogger(__name__)` in every module. No `print()` in business logic. Events surface to the CLI via the event system.

---

### Caption Generator

#### Platform registry `[REBUILD]`
- **Debt:** Plain dict with multiline string instructions and `{link}` placeholders — easy to break with a formatting mistake.
- **Rebuild approach:** `Platform` dataclass. Prompt building as a pure function in `core/captions.py`.

#### Transcript loader `[REBUILD]`
- **Debt:** File selection logic and type preference logic mixed together. Falls back through a chain of `if` checks.
- **Rebuild approach:** Query `stage_results` for transcript output paths. Type preference expressed as an ordered list, not a chain of conditionals.

#### Preview + approval loop `[REBUILD]`
- **Debt:** `while True` loop with string-matching on user input.
- **Rebuild approach:** `typer` prompt with explicit choices. State machine drives loop termination cleanly.

#### Single caption regeneration `[REBUILD]`
- **Debt:** Parses caption numbers with regex. Fragile if Gemini returns unexpected formatting.
- **Rebuild approach:** Captions stored as a list internally throughout the generation flow. Index-based replacement — no regex parsing.

#### Reference list generation `[REBUILD]`
- **Debt:** Called from inside the approval loop. Two concerns mixed.
- **Rebuild approach:** `build_reference_prompt()` isolated in `core/captions.py`. Called explicitly after approval by the CLI layer — not implicitly inside the approval loop.

#### Pending review `[REBUILD]`
- **Debt:** `_pending_review` filename suffix appended to pipeline-generated captions. Reviewed by renaming the file. Any file manager rename breaks the suffix logic.
- **Rebuild approach:** `reviewed` boolean column in `stage_results`. Filenames stay clean. Review state lives in the database.

#### Hook detection prompt `[POST-REBUILD]`
- **Why post-rebuild:** A prompt engineering task. Should be scoped and tested separately after the core rebuild is stable.

#### Dynamic template / sentiment-based layouts `[POST-REBUILD]`
- **Why post-rebuild:** Requires a sentiment analysis pass and multiple image templates. Out of rebuild scope.

---

### Image Generator

#### Cover art loader `[REBUILD]`
- **Debt:** Scans folder with string suffix matching. Uses `max()` by mtime as a fallback.
- **Rebuild approach:** Cover art path stored in `stage_results` after fetch. No folder scanning required.

#### Caption loader `[REBUILD]`
- **Debt:** Prefers `_pending_review` files in pipeline mode — tightly coupled to the filename convention from `caption.py`.
- **Rebuild approach:** Caption paths read from `stage_results`. No filename pattern matching.

#### Background brightness detection `[REBUILD]`
- **Debt:** Mixed into `imagegen.py` — a rendering concern that contains business logic.
- **Rebuild approach:** Pure function in `core/images.py`. Returns a `FontWeight` enum value.

#### Quote card generator `[REBUILD]`
- **Debt:** Monolithic function handling background, overlay, font, word wrap, shadow, and save in one block.
- **Rebuild approach:** Decomposed into composable steps in `core/images.py`: `build_background()`, `apply_overlay()`, `render_text()`. Each independently testable. `storage/episodes.py` handles saving.

#### Post-generation review `[REBUILD]`
- **Debt:** Review state tracked in a local list of dicts. Overlay opacity magic numbers hardcoded inline.
- **Rebuild approach:** Review state in `stage_results.reviewed`. Opacity values as named constants in `core/images.py`.

#### Waveform visualisation / live partial transcripts `[POST-REBUILD]`
- **Why post-rebuild:** GUI-phase features. Not applicable to the CLI.

#### Export formats (SRT, DOCX) `[POST-REBUILD]`
- **Why post-rebuild:** SRT maps cleanly to the existing segment transcript format and is low effort. Both are feature additions — scope after the rebuild stabilises.

---

### Pipeline Runner

#### Full Auto mode `[REBUILD]`
- **Debt:** Config as a plain dict. String key typos silently pass `None` to downstream functions.
- **Rebuild approach:** `PipelineConfig` as a `pydantic` model. Validated on construction. Attribute access, not string keys.

#### Guided Auto mode `[REBUILD]`
- **Debt:** Long sequential input chain with no inline validation. Mistakes early require redoing everything.
- **Rebuild approach:** `typer` prompts with inline validation. Pre-flight checks run before the decision map, not after.

#### Pre-flight validation `[REBUILD]`
- **Debt:** Runs after the user has answered all Guided Auto questions.
- **Rebuild approach:** API key format check and ffmpeg check run before any user prompts. User is informed of constraints before committing to a configuration.

#### Config template `[REBUILD]`
- **Debt:** `pipeline_config.json` flat file.
- **Rebuild approach:** Row in `setup` table keyed by config name.

#### Episode validator `[REBUILD]`
- **Debt:** Parses the RSS feed a second time solely to validate — redundant if the feed was just loaded for selection.
- **Rebuild approach:** Validation occurs during the `services/rss.py` fetch operation. Not a separate step.

#### Pending review scanner `[REBUILD]`
- **Debt:** Scans the filesystem for `_pending_review` filename suffix.
- **Rebuild approach:** `SELECT * FROM stage_results WHERE stage = 'CAPTIONS' AND reviewed = 0`.

#### `pipeline_run.log` `[REBUILD]`
- **Debt:** Append-only plain text file. Not machine-readable. Hard to query for run time estimates.
- **Rebuild approach:** All run data in `stage_results`. Structured JSON log via `logger.py` for field debugging. Estimated run time queried from `stage_results.duration_ms`.

#### Completion notification `[REBUILD]`
- **Debt:** `plyer` imported at module level. Import fails before the fallback runs if the library is absent.
- **Rebuild approach:** Lazy import inside the notification function. Falls back to terminal bell silently.

#### Queue-based decoupling / Kafka / RabbitMQ `[CUT]`
- **Why cut:** Appropriate architecture for multi-tenant SaaS under concurrent load. Transcrire is a single-user local tool. The `core/` / `services/` separation already solves provider-swapping without queue infrastructure. Revisit only if the product goes multi-tenant.

#### Event-driven WebSockets / job IDs `[POST-REBUILD]`
- **Why post-rebuild:** The event emitter in the rebuild provides the hooks. WebSocket handlers are a GUI-phase addition.

#### Output versioning `[POST-REBUILD]`
- **Why post-rebuild:** `version` and `input_hash` columns are present in the schema. Logic to populate them and manage versioned filenames is deferred.

#### API cost and token tracking `[POST-REBUILD]`
- **Why post-rebuild:** `cost_usd` and `tokens_used` columns are present in the schema. No logic built against them in the rebuild.

---

### Chunker (absorbed, no longer a standalone module)

#### `chunker.py` `[CUT as standalone]`
- **Debt:** Imported via `importlib.util` — a workaround for poor module structure. Checkpoint as JSON file.
- **Rebuild approach:** Chunking logic absorbed into `services/audio.py` and `core/transcript.py`. Checkpoint in `setup` table. `chunker.py` does not exist in the rebuild.

---

### Shared Utilities

#### `format_time()` `[REBUILD]`
- **Debt:** Returns a formatted string directly. Inconsistent with Python's `timedelta`.
- **Rebuild approach:** Display utility only, lives in `cli/`. Core code uses `timedelta` internally.

#### `load_metadata()` `[CUT]`
- **Why cut:** `metadata.json` is eliminated. Replaced by `storage/db.py` queries.

#### `METADATA_PATH` constant `[CUT]`
- **Why cut:** No `metadata.json` in the rebuild.

---

### Cleanup Utility

#### Folder + state file cleanup `[REBUILD]`
- **Debt:** Two separate loops for one conceptual operation. `delete_folder_contents()` returns `None` instead of `(0, 0)` when a folder is not found — fragile tuple unpacking.
- **Rebuild approach:** `transcrire clean` as a `typer` command. Database rows cleared alongside files in a single transaction — either everything clears or nothing does.

#### Confirmation gate `[REBUILD]`
- **Debt:** Plain `input()` string comparison.
- **Rebuild approach:** `typer.confirm()` with a `--force` flag for scripted use.

---

### Windows Installer (`Transcrire.cmd`)

#### First-run installer `[REBUILD]`
- **Debt:** `curl` + `PowerShell Expand-Archive` combo is fragile on some Windows configurations. `user_paths.py` written as a path override hack. Manual `pip install` in batch script.
- **Rebuild approach:** `uv` bootstrapped silently via standalone binary. `uv sync` from `uv.lock` for reproducible install. `pydantic-settings` handles all path overrides via environment variables — no `user_paths.py` required.

#### File separation (AppData vs Desktop) `[REBUILD]`
- **Debt:** Env vars read with scattered `os.environ.get()` calls throughout the codebase.
- **Rebuild approach:** `pydantic-settings` reads `TRANSCRIRE_*` env vars with typed defaults. Single config object, one import, one place to change.

---

## 15. Testing Strategy

The `core/` separation makes testing straightforward. All pure functions in `core/` are unit tested without mocking.

```
tests/
├── core/
│   ├── test_transcript.py      ← timestamp offsetting, stitching, formatting
│   ├── test_captions.py        ← prompt building, caption parsing, list operations
│   ├── test_images.py          ← brightness detection, word wrap, overlay constants
│   └── test_pipeline.py        ← state derivation, completion level, available actions
├── services/
│   ├── test_rss.py             ← feed parsing (fixture XML; no live network)
│   └── test_audio.py           ← ffmpeg wrapper (requires ffmpeg; marked integration)
└── storage/
    ├── test_db.py              ← schema creation, queries, state derivation, WAL
    └── test_episodes.py        ← folder creation, manifest write, path resolution
```

Services tests are marked `@pytest.mark.integration` and excluded from fast runs. All `core/` and `storage/` tests run without network access or external tools.

---

## 16. What's Explicitly Out of Scope for the Rebuild

| Feature | Status | Notes |
|---|---|---|
| GUI (Flask/FastAPI + React) | `[POST-REBUILD]` | Same `core/` layer; new interface layered on top |
| WebSockets / async progress | `[POST-REBUILD]` | Event system provides the hooks; handlers are GUI-phase |
| Waveform visualisation | `[POST-REBUILD]` | GUI-phase feature |
| Live partial transcripts | `[POST-REBUILD]` | GUI-phase feature |
| SRT export | `[POST-REBUILD]` | Low effort; scope after rebuild stabilises |
| DOCX export | `[POST-REBUILD]` | Same |
| Hook detection prompt | `[POST-REBUILD]` | Prompt engineering task; design separately |
| Dynamic image templates | `[POST-REBUILD]` | Requires sentiment analysis pass |
| Output versioning | `[POST-REBUILD]` | Schema columns present; logic deferred |
| API cost / token tracking | `[POST-REBUILD]` | Schema columns present; logic deferred |
| Multi-user / queue architecture | `[POST-REBUILD]` | Only relevant if product goes multi-tenant |
| Auto-posting to WhatsApp | `[POST-REBUILD]` | API availability pending |
| Scheduled RSS runs | `[POST-REBUILD]` | After GUI phase |
| Mac/Linux support | `[POST-REBUILD]` | Windows-only for rebuild; `pathlib` usage keeps it portable |
| Chunk-level checkpointing (Groq) | `[CUT]` | Groq is fast enough; stage-level restart is acceptable |
| `chunker.py` as standalone module | `[CUT]` | Logic absorbed into `services/` and `core/` |

---

## 17. Build Order

1. **Project scaffolding** — `uv` init, `pyproject.toml`, folder structure, `config.py`, `logger.py`, `events.py`
2. **Domain layer** — `domain/enums.py`, `domain/episode.py`, `domain/stage_result.py`
3. **Database layer** — SQLite schema, `storage/db.py`, WAL config, migrations
4. **Services layer** — `rss.py`, `audio.py`, `groq.py`, `whisper.py`, `gemini.py` (all with `tenacity` backoff)
5. **Core layer** — `transcript.py`, `captions.py`, `images.py`, `pipeline.py`
6. **Storage layer** — `episodes.py` (manifest write included), `assets.py`
7. **CLI layer** — `main.py`, `rss.py`, `pc.py` (state-aware menu, event handlers registered here)
8. **Installer** — updated `Transcrire.cmd` with silent `uv` bootstrap
9. **Tests** — written alongside each layer, not after

---

## 18. Resolved Open Questions

| # | Question | Resolution | Justification |
|---|---|---|---|
| 1 | Database location | Hybrid: primary DB in `%APPDATA%\Transcrire\`, manifest sidecar in each episode folder | DB is authoritative at runtime. Manifest enables `transcrire recover` when DB is lost or folder is moved to a new machine. |
| 2 | Dependency management | Silent `uv` bootstrap in `Transcrire.cmd`. `uv sync` from lockfile. `pip` as developer fallback. | Speed and reproducibility without user complexity. |
| 3 | CLI framework | `typer` for command structure; entry point is a state-aware guided loop, not a static menu. | Intent-based UX. Available actions derived from episode state, not hardcoded option lists. |
