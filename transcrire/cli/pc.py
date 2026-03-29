# ============================================================
# Transcrire — PC Upload CLI
# ============================================================
# Transcription-only path for audio files already on disk.
# No fetch, captions, or images.
# ============================================================

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import typer

from transcrire.domain.enums import TranscribeMode, TranscriptType
from transcrire.events import emit
from transcrire.storage.db import Database

logger = logging.getLogger(__name__)


def pc_upload_menu(db: Database) -> None:
    """
    PC Upload transcription flow.
    Prompts for file path, mode, and transcript type.
    Saves to pc_transcripts folder.
    Optionally copies to a user-specified destination.
    """
    typer.echo("\n" + "=" * 42)
    typer.echo("     💻  PC UPLOAD — TRANSCRIBE")
    typer.echo("=" * 42)
    typer.echo("\nTranscribes any audio file on your computer.")
    typer.echo("No captions or images will be generated.\n")

    # ---- File path ----
    raw_path = typer.prompt("Paste the full path to your audio file").strip().strip('"\'"')
    audio_path = Path(raw_path)

    from transcrire.storage.assets import validate_audio_path
    try:
        validate_audio_path(audio_path)
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"\n⚠️  {e}", err=True)
        return

    # ---- Mode ----
    typer.echo("\nTranscription mode:")
    typer.echo("  1.  Fast — Groq API (requires internet)")
    typer.echo("  2.  Offline — Whisper small (no internet needed)")
    mode_choice = typer.prompt("Select", default="1").strip()
    mode = TranscribeMode.GROQ if mode_choice == "1" else TranscribeMode.WHISPER

    # ---- Transcript type ----
    typer.echo("\nTranscript type:")
    typer.echo("  1.  Plain text")
    typer.echo("  2.  Segment level (timestamped by phrase)")
    typer.echo("  3.  Word level (timestamped by word)")
    type_choice = typer.prompt("Select", default="2").strip()
    type_map = {
        "1": TranscriptType.PLAIN,
        "2": TranscriptType.SEGMENTS,
        "3": TranscriptType.WORDS,
    }
    transcript_type = type_map.get(type_choice, TranscriptType.SEGMENTS)

    # ---- Copy to temp input location ----
    from transcrire.config import settings
    temp_path = settings.input_folder / f"_temp_{audio_path.name}"
    settings.input_folder.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(audio_path, temp_path)
    except Exception as e:
        typer.echo(f"\n⚠️  Could not load file: {e}", err=True)
        return

    # ---- Transcribe ----
    typer.echo(f"\nTranscribing: {audio_path.name}")
    start = time.time()

    try:
        if mode == TranscribeMode.GROQ:
            from transcrire.services.groq import transcribe_groq, GroqFileTooLargeError, GroqAuthError
            try:
                transcript = transcribe_groq(temp_path, transcript_type)
            except GroqFileTooLargeError:
                typer.echo("\n⚡  File too large for Groq — falling back to offline Whisper.")
                emit("groq_fallback", episode_id=None, reason="file_too_large")
                from transcrire.services.whisper import transcribe_whisper
                transcript = transcribe_whisper(temp_path, transcript_type)
            except GroqAuthError as e:
                typer.echo(f"\n❌  {e}", err=True)
                return
        else:
            from transcrire.services.whisper import transcribe_whisper
            transcript = transcribe_whisper(temp_path, transcript_type)

    except Exception as e:
        typer.echo(f"\n❌  Transcription failed: {e}", err=True)
        return
    finally:
        temp_path.unlink(missing_ok=True)

    elapsed = round(time.time() - start, 2)
    typer.echo(f"\nTranscription complete in {elapsed}s")

    # ---- Save to pc_transcripts ----
    from transcrire.storage.episodes import save_pc_transcript
    output_path = save_pc_transcript(
        transcript, audio_path.name, suffix=transcript_type.filename_suffix
    )
    typer.echo(f"\n✅  Transcript saved to: {output_path}")

    # ---- Optional copy ----
    if typer.confirm("\nCopy to a different folder?", default=False):
        dest_folder = typer.prompt("Destination folder path").strip().strip('"\'"')
        dest = Path(dest_folder)
        try:
            dest.mkdir(parents=True, exist_ok=True)
            dest_path = dest / output_path.name
            shutil.copy2(output_path, dest_path)
            typer.echo(f"✅  Also saved to: {dest_path}")
        except Exception as e:
            typer.echo(f"\n⚠️  Could not copy: {e}")
