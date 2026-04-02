# ============================================================
# Transcrire — RSS Pipeline CLI
# ============================================================
# State-aware RSS pipeline menu.
# Renders available actions derived from episode state.
# No logic lives here — all decisions come from core/pipeline.
# ============================================================

from __future__ import annotations

import logging
import time
from pathlib import Path

import typer

from transcrire.core.pipeline import (
    get_available_actions,
    format_duration,
    validate_api_keys,
)
from transcrire.domain.enums import (
    FetchChoice,
    Stage,
    TranscribeMode,
    TranscriptType,
)
from transcrire.domain.episode import Episode
from transcrire.events import emit
from transcrire.storage.db import Database

logger = logging.getLogger(__name__)


# ============================================================
# MENU RENDERING
# ============================================================

def print_rss_menu(episode: Episode | None, db: Database) -> None:
    """Renders the state-aware RSS pipeline menu."""
    typer.echo("\n" + "=" * 42)
    typer.echo("        🎙️  TRANSCRIRE — RSS")
    typer.echo("=" * 42)

    if episode:
        short_title = episode.title[:30] + ("..." if len(episode.title) > 30 else "")
        typer.echo(f"  📻  {episode.identifier} — {short_title}")
        typer.echo(f"  📊  {episode.completion_level().value.title()}")
        typer.echo("-" * 42)

    actions = get_available_actions(episode)
    for action in actions:
        prefix = "▶" if action.is_primary else " "
        typer.echo(f"  {action.key}.  {prefix} {action.label}")

    typer.echo("-" * 42)
    typer.echo("  0.    Back to source selection")

    # Show pending review count if any
    pending = db.get_pending_review()
    if pending:
        typer.echo(f"\n  📋  {len(pending)} caption file(s) awaiting review  [R]")

    typer.echo("=" * 42)


# ============================================================
# RSS PIPELINE MENU LOOP
# ============================================================

def rss_pipeline_menu(db: Database) -> None:
    """
    Main RSS pipeline loop.
    Loads the most recent active episode from DB on entry,
    re-derives state after every action.
    """
    episode = _load_active_episode(db)

    while True:
        print_rss_menu(episode, db)
        choice = typer.prompt("\nSelect").strip().upper()

        if choice == "0":
            return

        if choice == "R":
            _review_pending_captions(db)
            continue

        # Map choice to action
        actions = get_available_actions(episode)
        action  = next((a for a in actions if a.key == choice), None)

        if not action:
            typer.echo("\n⚠️  Invalid choice.")
            continue

        # Dispatch to the appropriate handler
        if action.stage == Stage.FETCH:
            episode = _run_fetch(db)

        elif action.stage == Stage.TRANSCRIBE and episode:
            _run_transcribe(db, episode)
            episode = db.get_episode_by_id(episode.id)

        elif action.stage == Stage.CAPTIONS and episode:
            _run_captions(db, episode)
            episode = db.get_episode_by_id(episode.id)

        elif action.stage == Stage.IMAGES and episode:
            _run_images(db, episode)
            episode = db.get_episode_by_id(episode.id)

        elif action.stage is None:
            # Non-pipeline actions
            if "summary" in action.label.lower() and episode:
                _show_summary(episode)
            elif "transcript" in action.label.lower() and episode:
                _show_transcript_path(episode)
            elif "error" in action.label.lower() and episode:
                _show_error_details(episode)
            elif "caption" in action.label.lower() and episode:
                _show_captions_path(episode)
            elif "image" in action.label.lower() and episode:
                _show_images_path(episode)


# ============================================================
# PIPELINE STAGE RUNNERS
# ============================================================

def _run_fetch(db: Database) -> Episode | None:
    """Runs the fetch stage interactively."""
    from transcrire.services.rss import find_episode, fetch_feed, EpisodeNotFoundError, FeedError
    from transcrire.storage.episodes import (
        create_episode_folder, download_audio, download_cover_art, write_manifest
    )
    from transcrire.domain.episode import Episode
    from transcrire.domain.stage_result import StageResult
    from transcrire.domain.enums import Stage, Status
    import sqlite3

    # ---- Select podcast ----
    feeds = db.list_feeds()
    if not feeds:
        typer.echo("\n⚠️  No saved podcasts. Enter an RSS URL to get started.")
        rss_url = typer.prompt("RSS feed URL").strip()
        try:
            result = fetch_feed(rss_url)
            db.save_feed(result.podcast_name, rss_url)
            typer.echo(f"✅  Saved: {result.podcast_name}")
            feeds = db.list_feeds()
        except FeedError as e:
            typer.echo(f"\n❌  {e}", err=True)
            return None

    typer.echo("\nSaved podcasts:")
    for i, (name, _) in enumerate(feeds, 1):
        typer.echo(f"  {i}.  {name}")
    typer.echo("  0.  Add new podcast")

    feed_choice = typer.prompt("Select").strip()

    if feed_choice == "0":
        rss_url = typer.prompt("RSS feed URL").strip()
        try:
            result = fetch_feed(rss_url)
            db.save_feed(result.podcast_name, rss_url)
            podcast_name = result.podcast_name
            typer.echo(f"✅  Saved: {podcast_name}")
        except FeedError as e:
            typer.echo(f"\n❌  {e}", err=True)
            return None
    elif feed_choice.isdigit() and 1 <= int(feed_choice) <= len(feeds):
        podcast_name, rss_url = feeds[int(feed_choice) - 1]
    else:
        typer.echo("\n⚠️  Invalid choice.")
        return None

    # ---- Season + episode ----
    season  = typer.prompt("Season number").strip()
    episode_num = typer.prompt("Episode number").strip()

    if not season.isdigit() or not episode_num.isdigit():
        typer.echo("\n⚠️  Season and episode must be numbers.")
        return None

    season, episode_num = int(season), int(episode_num)

    # ---- Fetch choice ----
    typer.echo("\nWhat would you like to fetch?")
    typer.echo("  1.  Audio only")
    typer.echo("  2.  Cover art only")
    typer.echo("  3.  Spotify link only")
    typer.echo("  4.  All (recommended)")
    fetch_choice = typer.prompt("Select", default="4").strip()

    fetch_map = {
        "1": FetchChoice.AUDIO,
        "2": FetchChoice.COVER,
        "3": FetchChoice.LINK,
        "4": FetchChoice.ALL,
    }
    chosen_fetch = fetch_map.get(fetch_choice, FetchChoice.ALL)

    # ---- Validate API keys before starting ----
    from transcrire.config import settings
    warnings = validate_api_keys(settings.gemini_api_key, settings.groq_api_key)
    for w in warnings:
        typer.echo(f"\n⚠️  {w}")

    # ---- Find episode in feed ----
    typer.echo(f"\nSearching feed for S{season}E{episode_num}...")
    start = time.time()

    try:
        assets = find_episode(rss_url, season, episode_num)
    except EpisodeNotFoundError as e:
        typer.echo(f"\n❌  {e}", err=True)
        return None
    except FeedError as e:
        typer.echo(f"\n❌  {e}", err=True)
        return None

    typer.echo(f"Found: {assets.title}")

    # ---- Create episode in DB ----
    episode = Episode(
        podcast_name = podcast_name,
        season       = season,
        episode      = episode_num,
        title        = assets.title,
        safe_title   = assets.safe_title,
        spotify_link = assets.spotify_link,
    )

    try:
        episode = db.create_episode(episode)
    except sqlite3.IntegrityError:
        typer.echo("\n⚠️  Episode already in database.")
        existing = db.get_episode(podcast_name, season, episode_num)
        if existing:
            typer.echo(f"   Previously processed: {existing.identifier}")
            if not typer.confirm("Process again?"):
                return existing
            episode = existing

    # ---- Create folder ----
    paths   = create_episode_folder(assets.safe_title, season, episode_num)
    episode.folder_path = paths.root
    db.update_episode_folder(episode.id, paths.root)

    emit("stage_started", stage="FETCH", episode_id=episode.id)

    output_paths = [str(paths.root)]

    # ---- Download assets ----
    if chosen_fetch in (FetchChoice.AUDIO, FetchChoice.ALL):
        if assets.audio_url:
            try:
                audio_path = download_audio(assets.audio_url, episode)
                output_paths.append(str(audio_path))
                typer.echo(f"✅  Audio saved: {audio_path.name}")
            except Exception as e:
                typer.echo(f"\n⚠️  Audio download failed: {e}")
        else:
            typer.echo("\n⚠️  No audio URL found in feed.")

    if chosen_fetch in (FetchChoice.COVER, FetchChoice.ALL):
        if assets.cover_url:
            try:
                cover_path = download_cover_art(assets.cover_url, episode, paths)
                output_paths.append(str(cover_path))
                typer.echo(f"✅  Cover art saved: {cover_path.name}")
            except Exception as e:
                typer.echo(f"\n⚠️  Cover art download failed: {e}")
        else:
            typer.echo("\n⚠️  No cover art found in feed.")

    if chosen_fetch in (FetchChoice.LINK, FetchChoice.ALL):
        if assets.spotify_link:
            typer.echo(f"✅  Spotify link: {assets.spotify_link}")

    # ---- Record stage result ----
    duration_ms = int((time.time() - start) * 1000)
    result = StageResult(
        episode_id   = episode.id,
        stage        = Stage.FETCH,
        status       = Status.COMPLETED,
        output_paths = [Path(p) for p in output_paths],
        duration_ms  = duration_ms,
    )
    db.record_stage_result(result)
    episode.stage_results.append(result)

    # ---- Write manifest ----
    write_manifest(episode, episode.stage_results)

    emit("stage_completed", stage="FETCH", episode_id=episode.id, duration_ms=duration_ms)

    return db.get_episode_by_id(episode.id)


def _run_transcribe(db: Database, episode: Episode) -> None:
    """Runs the transcribe stage interactively."""
    from transcrire.storage.assets import find_audio_files, most_recent_audio
    from transcrire.storage.episodes import save_transcript, write_manifest
    from transcrire.domain.stage_result import StageResult
    from transcrire.domain.enums import Stage, Status

    # ---- Select audio file ----
    audio_files = find_audio_files()
    if not audio_files:
        typer.echo("\n⚠️  No audio files found in input folder.")
        typer.echo("   Run Fetch first, or add an audio file to the input folder.")
        return

    if len(audio_files) == 1:
        audio_path = audio_files[0]
        typer.echo(f"\nUsing: {audio_path.name}")
    else:
        typer.echo("\nAudio files in input folder:")
        for i, f in enumerate(audio_files, 1):
            typer.echo(f"  {i}.  {f.name}")
        typer.echo("  0.  Use most recent")
        choice = typer.prompt("Select", default="0").strip()
        if choice == "0":
            audio_path = audio_files[0]
        elif choice.isdigit() and 1 <= int(choice) <= len(audio_files):
            audio_path = audio_files[int(choice) - 1]
        else:
            typer.echo("\n⚠️  Invalid choice.")
            return

    # ---- Mode selection ----
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
    type_map = {"1": TranscriptType.PLAIN, "2": TranscriptType.SEGMENTS, "3": TranscriptType.WORDS}
    transcript_type = type_map.get(type_choice, TranscriptType.SEGMENTS)

    # ---- Transcribe ----
    typer.echo(f"\nTranscribing {audio_path.name}...")
    emit("stage_started", stage="TRANSCRIBE", episode_id=episode.id)
    start = time.time()

    try:
        if mode == TranscribeMode.GROQ:
            from transcrire.services.groq import transcribe_groq, GroqFileTooLargeError, GroqAuthError
            try:
                transcript = transcribe_groq(audio_path, transcript_type)
            except GroqFileTooLargeError:
                typer.echo("\n⚡  File too large for Groq — falling back to offline Whisper.")
                emit("groq_fallback", episode_id=episode.id, reason="file_too_large")
                from transcrire.services.whisper import transcribe_whisper
                transcript = transcribe_whisper(audio_path, transcript_type, episode.id)
            except GroqAuthError as e:
                typer.echo(f"\n❌  {e}", err=True)
                return
        else:
            from transcrire.services.whisper import transcribe_whisper
            transcript = transcribe_whisper(audio_path, transcript_type, episode.id)

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        result = StageResult(
            episode_id  = episode.id,
            stage       = Stage.TRANSCRIBE,
            status      = Status.FAILED,
            error       = str(e),
            duration_ms = duration_ms,
        )
        db.record_stage_result(result)
        emit("stage_failed", stage="TRANSCRIBE", episode_id=episode.id, error=str(e))
        typer.echo(f"\n❌  Transcription failed: {e}", err=True)
        return

    # ---- Save transcript ----
    from transcrire.storage.episodes import EpisodePaths
    paths = EpisodePaths(
        root        = episode.folder_path,
        transcripts = episode.folder_path / "transcripts",
        captions    = episode.folder_path / "captions",
        images      = episode.folder_path / "images",
    )

    output_path = save_transcript(
        transcript, episode, paths, suffix=transcript_type.filename_suffix
    )

    duration_ms = int((time.time() - start) * 1000)
    result = StageResult(
        episode_id   = episode.id,
        stage        = Stage.TRANSCRIBE,
        status       = Status.COMPLETED,
        output_paths = [output_path],
        duration_ms  = duration_ms,
    )
    db.record_stage_result(result)
    episode.stage_results.append(result)
    write_manifest(episode, episode.stage_results)
    emit("stage_completed", stage="TRANSCRIBE", episode_id=episode.id, duration_ms=duration_ms)


def _run_captions(db: Database, episode: Episode) -> None:
    """Runs the captions stage interactively."""
    from transcrire.core.captions import (
        PLATFORMS, build_caption_prompt, parse_captions,
        format_captions, strip_urls, build_single_caption_prompt,
        build_reference_prompt, replace_caption,
    )
    from transcrire.services.gemini import generate_captions, generate_references, GeminiError
    from transcrire.storage.episodes import save_captions, save_references, write_manifest, EpisodePaths
    from transcrire.domain.stage_result import StageResult
    from transcrire.domain.enums import Stage, Status

    paths = EpisodePaths(
        root        = episode.folder_path,
        transcripts = episode.folder_path / "transcripts",
        captions    = episode.folder_path / "captions",
        images      = episode.folder_path / "images",
    )

    # ---- Load transcript ----
    transcript_files = sorted(paths.transcripts.glob("*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not transcript_files:
        typer.echo("\n⚠️  No transcript found. Run Transcribe first.")
        return

    typer.echo("\nAvailable transcripts:")
    for i, f in enumerate(transcript_files, 1):
        label = " ⏱️" if any(x in f.stem for x in ("_segments", "_words")) else ""
        typer.echo(f"  {i}.  {f.name}{label}")
    typer.echo("  0.  Use most recent")

    t_choice = typer.prompt("Select", default="0").strip()
    if t_choice == "0":
        transcript_path = transcript_files[0]
    elif t_choice.isdigit() and 1 <= int(t_choice) <= len(transcript_files):
        transcript_path = transcript_files[int(t_choice) - 1]
    else:
        typer.echo("\n⚠️  Invalid choice.")
        return

    transcript     = transcript_path.read_text(encoding="utf-8")
    is_timestamped = any(x in transcript_path.stem for x in ("_segments", "_words"))
    spotify_link   = episode.spotify_link or ""

    # ---- Platform selection ----
    typer.echo("\nGenerate captions for:")
    platform_list = list(PLATFORMS.keys())
    for i, name in enumerate(platform_list, 1):
        typer.echo(f"  {i}.  {name.capitalize()}")
    typer.echo("  0.  All platforms")

    p_choice = typer.prompt("Select", default="0").strip()
    if p_choice == "0":
        selected_platforms = platform_list
    elif p_choice.isdigit() and 1 <= int(p_choice) <= len(platform_list):
        selected_platforms = [platform_list[int(p_choice) - 1]]
    else:
        typer.echo("\n⚠️  Invalid choice.")
        return

    emit("stage_started", stage="CAPTIONS", episode_id=episode.id)
    start        = time.time()
    output_paths = []

    for platform_name in selected_platforms:
        platform = PLATFORMS[platform_name]
        typer.echo(f"\nGenerating {platform_name.upper()} captions...")

        try:
            prompt       = build_caption_prompt(platform, transcript, spotify_link)
            raw_captions = generate_captions(prompt)
            captions     = parse_captions(raw_captions)
        except GeminiError as e:
            typer.echo(f"\n⚠️  {platform_name.upper()} failed: {e}")
            continue

        # ---- Preview and approval loop ----
        captions_text = format_captions(captions)
        while True:
            typer.echo(f"\n--- {platform_name.upper()} CAPTIONS ---\n")
            typer.echo(captions_text)
            typer.echo("\n" + "-" * 40)
            typer.echo("  1.  Approve and save")
            typer.echo("  2.  Regenerate all")
            typer.echo("  3.  Edit an individual caption")
            typer.echo("  4.  Skip this platform")

            decision = typer.prompt("Select").strip()

            if decision == "1":
                output = save_captions(captions_text, episode, paths, platform_name)
                output_paths.append(output)
                typer.echo(f"\n✅  {platform_name.upper()} captions saved.")

                if is_timestamped:
                    typer.echo("Generating reference list...")
                    try:
                        ref_prompt = build_reference_prompt(platform_name, transcript, captions_text)
                        references = generate_references(ref_prompt)
                        save_references(references, episode, paths, platform_name)
                        typer.echo("✅  Reference list saved.")
                    except Exception as e:
                        typer.echo(f"\n⚠️  Reference list failed: {e}")
                break

            elif decision == "2":
                typer.echo("\nRegenerating...")
                try:
                    raw_captions = generate_captions(prompt)
                    captions     = parse_captions(raw_captions)
                    captions_text = format_captions(captions)
                except GeminiError as e:
                    typer.echo(f"\n⚠️  Regeneration failed: {e}")

            elif decision == "3":
                typer.echo("\nWhich caption would you like to replace?")
                for i, cap in enumerate(captions, 1):
                    preview = cap[:80] + "..." if len(cap) > 80 else cap
                    typer.echo(f"  {i}.  {preview}")
                cap_choice = typer.prompt("Select (0 to cancel)").strip()
                if cap_choice == "0" or not cap_choice.isdigit():
                    continue
                cap_index = int(cap_choice) - 1
                if 0 <= cap_index < len(captions):
                    regen_prompt = build_single_caption_prompt(
                        platform, captions_text, captions[cap_index], spotify_link
                    )
                    try:
                        new_caption = generate_captions(regen_prompt)
                        captions    = replace_caption(captions, cap_index, new_caption.strip())
                        captions_text = format_captions(captions)
                        typer.echo(f"\n✅  Caption {int(cap_choice)} replaced.")
                    except GeminiError as e:
                        typer.echo(f"\n⚠️  Regeneration failed: {e}")

            elif decision == "4":
                typer.echo(f"\nSkipping {platform_name.upper()}.")
                break

            else:
                typer.echo("\n⚠️  Invalid choice.")

    duration_ms = int((time.time() - start) * 1000)

    if output_paths:
        result = StageResult(
            episode_id   = episode.id,
            stage        = Stage.CAPTIONS,
            status       = Status.COMPLETED,
            output_paths = output_paths,
            duration_ms  = duration_ms,
            reviewed     = False,
        )
    else:
        result = StageResult(
            episode_id  = episode.id,
            stage       = Stage.CAPTIONS,
            status      = Status.FAILED,
            error       = "No captions were saved.",
            duration_ms = duration_ms,
        )

    db.record_stage_result(result)
    episode.stage_results.append(result)
    write_manifest(episode, episode.stage_results)
    emit("stage_completed", stage="CAPTIONS", episode_id=episode.id, duration_ms=duration_ms)


def _run_images(db: Database, episode: Episode) -> None:
    """Runs the image generation stage interactively."""
    from transcrire.core.images import build_quote_card, OVERLAY_DEFAULT, OVERLAY_LIGHT, OVERLAY_DARK
    from transcrire.core.captions import strip_urls as caption_strip_urls
    from transcrire.storage.assets import ensure_fonts, find_cover_art
    from transcrire.storage.episodes import save_image, write_manifest, EpisodePaths
    from transcrire.domain.stage_result import StageResult
    from transcrire.domain.enums import Stage, Status
    import re

    paths = EpisodePaths(
        root        = episode.folder_path,
        transcripts = episode.folder_path / "transcripts",
        captions    = episode.folder_path / "captions",
        images      = episode.folder_path / "images",
    )

    # ---- Ensure fonts ----
    try:
        ensure_fonts()
    except Exception as e:
        typer.echo(f"\n⚠️  Font check failed: {e}")
        return

    # ---- Find cover art ----
    cover_path = find_cover_art(paths.images)
    if not cover_path:
        typer.echo("\n⚠️  No cover art found. Run Fetch with cover art first.")
        return

    typer.echo(f"\nUsing cover art: {cover_path.name}")

    emit("stage_started", stage="IMAGES", episode_id=episode.id)
    start        = time.time()
    output_paths = []
    generated    = []

    PLATFORM_COUNTS = {"twitter": 3, "facebook": 2}

    from transcrire.config import settings

    for platform, count in PLATFORM_COUNTS.items():
        caption_files = sorted(
            paths.captions.glob(f"*_{platform}_captions.txt"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not caption_files:
            typer.echo(f"\n⚠️  No {platform} captions found — skipping.")
            continue

        raw = caption_files[0].read_text(encoding="utf-8")

        # Parse captions
        from transcrire.core.captions import parse_captions
        captions = parse_captions(raw)[:count]

        typer.echo(f"\nGenerating {platform.upper()} quote cards...")

        for i, caption in enumerate(captions, 1):
            clean_caption = caption_strip_urls(caption)
            filename      = f"{episode.safe_title}_{platform}_quote{i}_square.jpg"
            output_path   = paths.images / filename

            try:
                image = build_quote_card(
                    cover_path      = cover_path,
                    quote_text      = clean_caption,
                    fonts_dir       = settings.fonts_dir,
                    overlay_opacity = OVERLAY_DEFAULT,
                    podcast_name    = episode.podcast_name,
                    episode_title   = episode.title,
                )
                save_image(image, output_path)
                typer.echo(f"  ✅  Saved: {filename}")
                output_paths.append(output_path)
                generated.append({
                    "output_path": output_path,
                    "cover_path":  cover_path,
                    "caption":     clean_caption,
                    "platform":    platform,
                    "index":       i,
                })
            except Exception as e:
                typer.echo(f"  ⚠️  Failed to generate {filename}: {e}")

    # ---- Post-generation review ----
    if generated:
        typer.echo(f"\n{len(generated)} image(s) generated.")
        if typer.confirm("\nReview images now?", default=False):
            for item in generated:
                preview = item["caption"][:60] + "..." if len(item["caption"]) > 60 else item["caption"]
                typer.echo(f"\n--- {item['platform'].upper()} Quote {item['index']} ---")
                typer.echo(f"Caption: \"{preview}\"")
                typer.echo(f"Saved:   {item['output_path']}")
                typer.echo("  1.  Approve")
                typer.echo("  2.  Lighter overlay")
                typer.echo("  3.  Darker overlay")
                typer.echo("  4.  Delete")

                r = typer.prompt("Select", default="1").strip()
                if r == "2":
                    image = build_quote_card(
                        item["cover_path"], item["caption"],
                        settings.fonts_dir, OVERLAY_LIGHT,
                    )
                    save_image(image, item["output_path"])
                    typer.echo("✅  Regenerated with lighter overlay.")
                elif r == "3":
                    image = build_quote_card(
                        item["cover_path"], item["caption"],
                        settings.fonts_dir, OVERLAY_DARK,
                    )
                    save_image(image, item["output_path"])
                    typer.echo("✅  Regenerated with darker overlay.")
                elif r == "4":
                    item["output_path"].unlink(missing_ok=True)
                    output_paths = [p for p in output_paths if p != item["output_path"]]
                    typer.echo("🗑️   Deleted.")

    duration_ms = int((time.time() - start) * 1000)
    result = StageResult(
        episode_id   = episode.id,
        stage        = Stage.IMAGES,
        status       = Status.COMPLETED if output_paths else Status.FAILED,
        output_paths = output_paths,
        duration_ms  = duration_ms,
    )
    db.record_stage_result(result)
    episode.stage_results.append(result)
    write_manifest(episode, episode.stage_results)
    emit("stage_completed", stage="IMAGES", episode_id=episode.id, duration_ms=duration_ms)


# ============================================================
# REVIEW HELPERS
# ============================================================

def _review_pending_captions(db: Database) -> None:
    pending = db.get_pending_review()
    if not pending:
        typer.echo("\n✅  No pending review captions.")
        return

    typer.echo(f"\n📋  {len(pending)} caption file(s) pending review:\n")
    for i, (ep, sr) in enumerate(pending, 1):
        typer.echo(f"  {i}.  [{ep.identifier}] {ep.title[:40]}")
        for p in sr.output_paths:
            typer.echo(f"       {p.name}")

    typer.echo("\n  A.  Mark all as reviewed")
    typer.echo("  0.  Back")
    choice = typer.prompt("\nSelect").strip().upper()

    if choice == "A":
        for _, sr in pending:
            db.mark_reviewed(sr.id)
        typer.echo(f"\n✅  {len(pending)} file(s) marked as reviewed.")
    elif choice.isdigit() and 1 <= int(choice) <= len(pending):
        _, sr = pending[int(choice) - 1]
        db.mark_reviewed(sr.id)
        typer.echo("\n✅  Marked as reviewed.")


# ============================================================
# DISPLAY HELPERS
# ============================================================

def _show_summary(episode: Episode) -> None:
    typer.echo(f"\n--- Episode Summary ---")
    typer.echo(f"Title    : {episode.title}")
    typer.echo(f"Podcast  : {episode.podcast_name}")
    typer.echo(f"Episode  : {episode.identifier}")
    typer.echo(f"State    : {episode.derive_state().value}")
    typer.echo(f"Level    : {episode.completion_level().value}")
    if episode.spotify_link:
        typer.echo(f"Link     : {episode.spotify_link}")
    typer.echo(f"Folder   : {episode.folder_path}")


def _show_transcript_path(episode: Episode) -> None:
    from transcrire.domain.enums import Stage
    result = episode.stage_result_for(Stage.TRANSCRIBE)
    if result and result.output_paths:
        typer.echo(f"\nTranscript: {result.output_paths[0]}")
    else:
        typer.echo("\n⚠️  No transcript found.")


def _show_captions_path(episode: Episode) -> None:
    from transcrire.domain.enums import Stage
    result = episode.stage_result_for(Stage.CAPTIONS)
    if result and result.output_paths:
        for p in result.output_paths:
            typer.echo(f"\nCaption: {p}")
    else:
        typer.echo("\n⚠️  No captions found.")


def _show_images_path(episode: Episode) -> None:
    from transcrire.domain.enums import Stage
    result = episode.stage_result_for(Stage.IMAGES)
    if result and result.output_paths:
        for p in result.output_paths:
            typer.echo(f"\nImage: {p}")
    else:
        typer.echo("\n⚠️  No images found.")


def _show_error_details(episode: Episode) -> None:
    last = episode.last_failed_stage
    if last:
        typer.echo(f"\n❌  Stage : {last.stage.value}")
        typer.echo(f"   Error  : {last.error}")
        typer.echo(f"   Time   : {last.created_at.isoformat()}")
    else:
        typer.echo("\n⚠️  No error details found.")


# ============================================================
# ACTIVE EPISODE LOADER
# ============================================================

def _load_active_episode(db: Database) -> Episode | None:
    """
    Loads the most recently created episode from the database.
    Returns None if no episodes exist yet.
    """
    episodes = db.list_episodes()
    if not episodes:
        return None
    latest = episodes[-1]
    return db.get_episode_by_id(latest.id)
