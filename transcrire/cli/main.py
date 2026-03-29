# ============================================================
# Transcrire — CLI Entry Point
# ============================================================
# State-aware guided menu loop.
# Calls pipeline.get_available_actions() on every render —
# never decides logic itself.
#
# Run via:
#   transcrire          (after uv sync)
#   python -m transcrire
# ============================================================

from __future__ import annotations
from pathlib import Path

import logging
import sys

import typer

from transcrire.events import on
from transcrire.logger import setup_logging
from transcrire.storage.db import Database

app = typer.Typer(
    name="transcrire",
    help="Podcast content pipeline — fetch, transcribe, caption, image.",
    add_completion=False,
    no_args_is_help=False,
)

logger = logging.getLogger(__name__)


# ============================================================
# EVENT HANDLERS
# Registered at startup — print human-readable progress
# to the terminal as the pipeline emits events.
# ============================================================

def _on_stage_started(stage: str, episode_id: int, **_) -> None:
    typer.echo(f"\n--- {stage.title()} ---")


def _on_stage_completed(stage: str, episode_id: int, duration_ms: int, **_) -> None:
    from transcrire.core.pipeline import format_duration
    typer.echo(f"\n✅  {stage.title()} complete ({format_duration(duration_ms)})")


def _on_stage_failed(stage: str, episode_id: int, error: str, **_) -> None:
    typer.echo(f"\n❌  {stage.title()} failed: {error}", err=True)


def _on_groq_fallback(episode_id: int, reason: str, **_) -> None:
    messages = {
        "file_too_large":   "Audio too large for Groq after compression.",
        "groq_api_failure": "Groq API call failed.",
        "no_internet":      "No internet connection detected.",
    }
    msg = messages.get(reason, "Groq unavailable.")
    typer.echo(
        f"\n⚡  Groq fallback: {msg} "
        f"Switching to offline Whisper — this may take significantly longer."
    )


def _on_checkpoint_saved(episode_id: int, chunk_index: int, total_chunks: int, **_) -> None:
    typer.echo(f"   Chunk {chunk_index}/{total_chunks} complete — progress saved.")


def _on_pipeline_complete(episode_id: int, completion_level: str, **_) -> None:
    typer.echo(f"\n🎙️  Pipeline complete — {completion_level}")


def register_event_handlers() -> None:
    on("stage_started",    _on_stage_started)
    on("stage_completed",  _on_stage_completed)
    on("stage_failed",     _on_stage_failed)
    on("groq_fallback",    _on_groq_fallback)
    on("checkpoint_saved", _on_checkpoint_saved)
    on("pipeline_complete", _on_pipeline_complete)


# ============================================================
# STARTUP
# ============================================================

def startup() -> Database:
    """
    Initialises logging, event handlers, and the database.
    Called once at the start of every session.
    """
    setup_logging()
    register_event_handlers()

    db = Database()
    db.init()
    return db


# ============================================================
# SOURCE SELECTION MENU
# ============================================================

def print_header() -> None:
    typer.echo("\n" + "=" * 42)
    typer.echo("        🎙️  TRANSCRIRE")
    typer.echo("=" * 42)


def source_menu(db: Database) -> None:
    """
    Top-level audio source selection loop.
    Routes to the RSS pipeline or PC upload path.
    """
    while True:
        print_header()
        typer.echo("  Select audio source:\n")
        typer.echo("  1.  Podcast RSS    (full pipeline)")
        typer.echo("  2.  PC Upload      (transcription only)")
        typer.echo("-" * 42)
        typer.echo("  0.  Exit")
        typer.echo("=" * 42)

        choice = typer.prompt("\nSelect").strip()

        if choice == "0":
            typer.echo("\nGoodbye! 👋")
            raise typer.Exit()

        elif choice == "1":
            from transcrire.cli.rss import rss_pipeline_menu
            rss_pipeline_menu(db)

        elif choice == "2":
            from transcrire.cli.pc import pc_upload_menu
            pc_upload_menu(db)

        else:
            typer.echo("\n⚠️  Invalid choice.")


# ============================================================
# CHECK COMMANDS
# ============================================================

@app.command("check")
def check_command(
    item: str = typer.Argument(
        "all",
        help="What to check: all, ffmpeg, api-keys, fonts",
    )
) -> None:
    """Run environment checks."""
    db = startup()

    if item in ("all", "ffmpeg"):
        typer.echo("\nChecking ffmpeg...")
        try:
            from transcrire.services.audio import check_ffmpeg
            check_ffmpeg()
            typer.echo("✅  ffmpeg found.")
        except Exception as e:
            typer.echo(f"❌  {e}", err=True)

    if item in ("all", "api-keys"):
        typer.echo("\nChecking API keys...")
        from transcrire.config import settings
        from transcrire.core.pipeline import validate_api_keys
        warnings = validate_api_keys(settings.gemini_api_key, settings.groq_api_key)
        if warnings:
            for w in warnings:
                typer.echo(f"⚠️   {w}")
        else:
            typer.echo("✅  API keys look valid.")

    if item in ("all", "fonts"):
        typer.echo("\nChecking fonts...")
        from transcrire.storage.assets import ensure_fonts, fonts_present
        if fonts_present():
            typer.echo("✅  Fonts present.")
        else:
            typer.echo("Fonts not found — downloading...")
            try:
                ensure_fonts()
                typer.echo("✅  Fonts downloaded.")
            except Exception as e:
                typer.echo(f"❌  Font download failed: {e}", err=True)


# ============================================================
# CLEAN COMMAND
# ============================================================

@app.command("clean")
def clean_command(
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt."),
    all_data: bool = typer.Option(False, "--all", help="Also clear feeds table."),
) -> None:
    """Delete all episode files and database records."""
    db = startup()

    if not force:
        typer.echo("\nThis will delete ALL episode files and database records.")
        typer.echo("Saved podcast feeds will be preserved.\n")
        confirmed = typer.confirm("Are you sure?")
        if not confirmed:
            typer.echo("Clean cancelled.")
            raise typer.Exit()

    import shutil
    from transcrire.config import settings

    # Clear database
    db.clear_all()
    typer.echo("✅  Database cleared.")

    # Clear output folder contents
    if settings.output_folder.exists():
        for item in settings.output_folder.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        typer.echo("✅  Output folder cleared.")

    # Clear input folder contents
    if settings.input_folder.exists():
        for item in settings.input_folder.iterdir():
            item.unlink(missing_ok=True)
        typer.echo("✅  Input folder cleared.")

    typer.echo("\nAll clear. Ready for a new episode.")


# ============================================================
# RECOVER COMMAND
# ============================================================

@app.command("recover")
def recover_command(
    folder: Path = typer.Argument(..., help="Path to the episode output folder.")
) -> None:
    """Reconstruct a database entry from a manifest.json sidecar."""
    db = startup()

    from transcrire.storage.episodes import read_manifest
    from transcrire.domain.episode import Episode
    from transcrire.domain.enums import Stage, Status
    from transcrire.domain.stage_result import StageResult
    import sqlite3

    manifest = read_manifest(folder)
    if not manifest:
        typer.echo(f"❌  No manifest.json found in {folder}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nFound manifest: {manifest.get('title', 'Unknown')}")
    typer.echo(f"Podcast: {manifest.get('podcast_name')}")
    typer.echo(f"Episode: S{manifest.get('season')}E{manifest.get('episode')}")

    # Reconstruct Episode row
    episode = Episode(
        podcast_name = manifest["podcast_name"],
        season       = manifest["season"],
        episode      = manifest["episode"],
        title        = manifest.get("title", ""),
        safe_title   = manifest.get("safe_title", ""),
        spotify_link = manifest.get("spotify_link"),
        folder_path  = folder,
    )

    try:
        episode = db.create_episode(episode)
    except sqlite3.IntegrityError:
        typer.echo("⚠️   Episode already exists in database — updating folder path.")
        existing = db.get_episode(episode.podcast_name, episode.season, episode.episode)
        if existing:
            db.update_episode_folder(existing.id, folder)
            typer.echo("✅  Folder path updated.")
            raise typer.Exit()

    # Reconstruct stage results
    for stage_name, stage_data in manifest.get("stages", {}).items():
        try:
            result = StageResult(
                episode_id   = episode.id,
                stage        = Stage(stage_name),
                status       = Status(stage_data["status"]),
                output_paths = [Path(p) for p in stage_data.get("output_paths", [])],
            )
            db.record_stage_result(result)
        except Exception as e:
            typer.echo(f"⚠️   Could not restore stage {stage_name}: {e}")

    typer.echo(f"\n✅  Episode recovered successfully.")


# ============================================================
# DEFAULT COMMAND — LAUNCH MAIN MENU
# ============================================================

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the Transcrire interactive menu."""
    if ctx.invoked_subcommand is not None:
        return

    db = startup()
    source_menu(db)
