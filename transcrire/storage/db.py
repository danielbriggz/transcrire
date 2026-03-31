# ============================================================
# Transcrire — Database Layer
# ============================================================
# Single module responsible for:
#   - Creating and migrating the SQLite schema
#   - All read/write queries
#   - Connection management
#
# The database lives in %APPDATA%\Transcrire\transcrire.db
# (or the project root in development).
#
# Rules:
#   - All SQL lives here. No raw SQL anywhere else.
#   - All functions accept/return domain objects, not dicts.
#   - WAL mode is enabled on every connection for safe reads.
#
# Usage:
#   from transcrire.storage.db import Database
#   db = Database()
#   db.init()
# ============================================================

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from transcrire.config import settings
from transcrire.domain.enums import Stage, Status
from transcrire.domain.episode import Episode
from transcrire.domain.stage_result import StageResult

logger = logging.getLogger(__name__)


# ============================================================
# SCHEMA
# ============================================================

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT    NOT NULL,
    season          INTEGER NOT NULL,
    episode         INTEGER NOT NULL,
    title           TEXT,
    safe_title      TEXT,
    spotify_link    TEXT,
    folder_path     TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE(season, episode, podcast_name)
);

CREATE TABLE IF NOT EXISTS stage_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id),
    stage           TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    output_paths    TEXT,
    error           TEXT,
    duration_ms     INTEGER,
    reviewed        INTEGER NOT NULL DEFAULT 0,
    -- Reserved for POST-REBUILD (present but not populated in v1):
    version         INTEGER DEFAULT 1,
    input_hash      TEXT,
    cost_usd        REAL,
    tokens_used     INTEGER,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS feeds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_name    TEXT    NOT NULL UNIQUE,
    rss_url         TEXT    NOT NULL,
    added_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS setup (
    key             TEXT    PRIMARY KEY,
    value           TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);
"""


# ============================================================
# DATABASE CLASS
# ============================================================

class Database:
    """
    Manages the SQLite database connection and all queries.

    Instantiate once and reuse throughout the application.
    Call init() on first use to create tables if they don't exist.

    Example:
        db = Database()
        db.init()
        episode = db.get_episode(podcast_name="My Pod", season=6, episode=5)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        # Allow path override for tests — defaults to settings.db_path
        self._path = db_path or settings.db_path

    @contextmanager
    def _connect(self):
        """
        Context manager that yields a configured SQLite connection.
        WAL mode is set on every connection.
        Row factory is set so rows are accessible by column name.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ----------------------------------------------------------
    # INIT / MIGRATIONS
    # ----------------------------------------------------------

    def init(self) -> None:
        """
        Creates all tables if they don't exist.
        Safe to call on every launch — idempotent.
        """
        with self._connect() as conn:
            conn.executescript(SCHEMA)
        logger.info("Database initialised", extra={"path": str(self._path)})

    # ----------------------------------------------------------
    # EPISODES
    # ----------------------------------------------------------

    def create_episode(self, episode: Episode) -> Episode:
        """
        Inserts a new episode row.
        Raises sqlite3.IntegrityError if (season, episode, podcast_name)
        already exists — callers should catch this for duplicate handling.
        """
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO episodes
                    (podcast_name, season, episode, title, safe_title,
                     spotify_link, folder_path, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode.podcast_name,
                    episode.season,
                    episode.episode,
                    episode.title,
                    episode.safe_title,
                    episode.spotify_link,
                    str(episode.folder_path) if episode.folder_path else None,
                    now,
                    now,
                ),
            )
            episode.id         = cursor.lastrowid
            episode.created_at = datetime.fromisoformat(now)
            episode.updated_at = datetime.fromisoformat(now)

        logger.info(
            "Episode created",
            extra={"episode_id": episode.id, "identifier": episode.identifier},
        )
        return episode

    def get_episode(
        self,
        podcast_name: str,
        season: int,
        episode: int,
    ) -> Episode | None:
        """
        Fetches an episode by its unique (podcast_name, season, episode) key.
        Returns None if not found.
        Populates stage_results automatically.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM episodes
                WHERE podcast_name = ? AND season = ? AND episode = ?
                """,
                (podcast_name, season, episode),
            ).fetchone()

            if not row:
                return None

            ep = _episode_from_row(row)
            ep.stage_results = self._get_stage_results(conn, ep.id)
            return ep

    def get_episode_by_id(self, episode_id: int) -> Episode | None:
        """Fetches an episode by its database ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM episodes WHERE id = ?",
                (episode_id,),
            ).fetchone()

            if not row:
                return None

            ep = _episode_from_row(row)
            ep.stage_results = self._get_stage_results(conn, ep.id)
            return ep

    def update_episode_folder(self, episode_id: int, folder_path: Path) -> None:
        """
        Updates the folder_path for an episode.
        Called by transcrire recover when a folder is moved.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE episodes SET folder_path = ?, updated_at = ? WHERE id = ?",
                (str(folder_path), _now(), episode_id),
            )

    def list_episodes(self, podcast_name: str | None = None) -> list[Episode]:
        """
        Returns all episodes, optionally filtered by podcast.
        Does not populate stage_results — use get_episode_by_id() for that.
        """
        with self._connect() as conn:
            if podcast_name:
                rows = conn.execute(
                    "SELECT * FROM episodes WHERE podcast_name = ? ORDER BY season, episode",
                    (podcast_name,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM episodes ORDER BY podcast_name, season, episode"
                ).fetchall()
            return [_episode_from_row(r) for r in rows]

    # ----------------------------------------------------------
    # STAGE RESULTS
    # ----------------------------------------------------------

    def record_stage_result(self, result: StageResult) -> StageResult:
        """
        Inserts a new stage result row.
        Returns the result with its database ID populated.
        """
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO stage_results
                    (episode_id, stage, status, output_paths, error,
                     duration_ms, reviewed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.episode_id,
                    result.stage.value,
                    result.status.value,
                    result.output_paths_json(),
                    result.error,
                    result.duration_ms,
                    int(result.reviewed),
                    now,
                ),
            )
            result.id         = cursor.lastrowid
            result.created_at = datetime.fromisoformat(now)

        logger.info(
            "Stage result recorded",
            extra={
                "episode_id": result.episode_id,
                "stage":      result.stage.value,
                "status":     result.status.value,
            },
        )
        return result

    def mark_reviewed(self, stage_result_id: int) -> None:
        """
        Marks a stage result as reviewed by the user.
        Replaces the old _pending_review filename suffix rename.
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE stage_results SET reviewed = 1 WHERE id = ?",
                (stage_result_id,),
            )

    def get_pending_review(self) -> list[tuple[Episode, StageResult]]:
        """
        Returns all caption stage results that have not been reviewed.
        Used to display the pending review backlog.
        Replaces filesystem scan for _pending_review filename suffix.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT sr.*, e.podcast_name, e.season, e.episode, e.title
                FROM stage_results sr
                JOIN episodes e ON e.id = sr.episode_id
                WHERE sr.stage = ? AND sr.reviewed = 0 AND sr.status = ?
                ORDER BY sr.created_at DESC
                """,
                (Stage.CAPTIONS.value, Status.COMPLETED.value),
            ).fetchall()

        results = []
        for row in rows:
            ep = Episode(
                podcast_name=row["podcast_name"],
                season=row["season"],
                episode=row["episode"],
                title=row["title"] or "",
                id=row["episode_id"],
            )
            sr = _stage_result_from_row(row)
            results.append((ep, sr))
        return results

    def _get_stage_results(
        self,
        conn: sqlite3.Connection,
        episode_id: int,
    ) -> list[StageResult]:
        """Fetches all stage results for an episode. Internal use only."""
        rows = conn.execute(
            "SELECT * FROM stage_results WHERE episode_id = ? ORDER BY created_at",
            (episode_id,),
        ).fetchall()
        return [_stage_result_from_row(r) for r in rows]

    # ----------------------------------------------------------
    # FEEDS
    # ----------------------------------------------------------

    def save_feed(self, podcast_name: str, rss_url: str) -> None:
        """
        Saves or updates a podcast RSS feed.
        Replaces feeds.json.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feeds (podcast_name, rss_url, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(podcast_name) DO UPDATE SET rss_url = excluded.rss_url
                """,
                (podcast_name, rss_url, _now()),
            )

    def get_feed(self, podcast_name: str) -> str | None:
        """Returns the RSS URL for a podcast, or None if not saved."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rss_url FROM feeds WHERE podcast_name = ?",
                (podcast_name,),
            ).fetchone()
            return row["rss_url"] if row else None

    def list_feeds(self) -> list[tuple[str, str]]:
        """
        Returns all saved feeds as (podcast_name, rss_url) tuples.
        Replaces reading feeds.json.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT podcast_name, rss_url FROM feeds ORDER BY podcast_name"
            ).fetchall()
            return [(r["podcast_name"], r["rss_url"]) for r in rows]

    def delete_feed(self, podcast_name: str) -> None:
        """Removes a saved RSS feed."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM feeds WHERE podcast_name = ?",
                (podcast_name,),
            )

    # ----------------------------------------------------------
    # SETUP
    # ----------------------------------------------------------

    def get_setup(self, key: str) -> str | None:
        """
        Reads a value from the setup table.
        Replaces reading setup.json, pipeline_config.json,
        and transcription_checkpoint.json.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM setup WHERE key = ?",
                (key,),
            ).fetchone()
            return row["value"] if row else None

    def set_setup(self, key: str, value: str) -> None:
        """Writes or updates a value in the setup table."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO setup (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, _now()),
            )

    def delete_setup(self, key: str) -> None:
        """Removes a key from the setup table."""
        with self._connect() as conn:
            conn.execute("DELETE FROM setup WHERE key = ?", (key,))

    def get_setup_json(self, key: str) -> dict | list | None:
        """Convenience wrapper — reads a JSON value from the setup table."""
        raw = self.get_setup(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_setup_json(self, key: str, value: dict | list) -> None:
        """Convenience wrapper — writes a JSON value to the setup table."""
        self.set_setup(key, json.dumps(value))

    # ----------------------------------------------------------
    # CLEANUP
    # ----------------------------------------------------------

    def clear_episode(self, episode_id: int) -> None:
        """
        Deletes an episode and all its stage results.
        Called by transcrire clean. Runs in a single transaction.
        """
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM stage_results WHERE episode_id = ?",
                (episode_id,),
            )
            conn.execute(
                "DELETE FROM episodes WHERE id = ?",
                (episode_id,),
            )

    def clear_all(self) -> None:
        """
        Deletes all episodes, stage results and setup entries.
        Feeds are preserved — the user's saved podcasts survive a clean.
        Called by transcrire clean --all.
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM stage_results")
            conn.execute("DELETE FROM episodes")
            conn.execute("DELETE FROM setup")


# ============================================================
# PRIVATE HELPERS
# ============================================================

def _now() -> str:
    """Returns the current UTC time as an ISO 8601 string."""
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()


def _episode_from_row(row: sqlite3.Row) -> Episode:
    """Constructs an Episode dataclass from a database row."""
    return Episode(
        id           = row["id"],
        podcast_name = row["podcast_name"],
        season       = row["season"],
        episode      = row["episode"],
        title        = row["title"] or "",
        safe_title   = row["safe_title"] or "",
        spotify_link = row["spotify_link"],
        folder_path  = Path(row["folder_path"]) if row["folder_path"] else None,
        created_at   = datetime.fromisoformat(row["created_at"]),
        updated_at   = datetime.fromisoformat(row["updated_at"]),
    )


def _stage_result_from_row(row: sqlite3.Row) -> StageResult:
    """Constructs a StageResult dataclass from a database row."""
    return StageResult(
        id           = row["id"],
        episode_id   = row["episode_id"],
        stage        = Stage(row["stage"]),
        status       = Status(row["status"]),
        output_paths = StageResult.output_paths_from_json(row["output_paths"]),
        error        = row["error"],
        duration_ms  = row["duration_ms"],
        reviewed     = bool(row["reviewed"]),
        created_at   = datetime.fromisoformat(row["created_at"]),
    )
