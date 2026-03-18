# ============================================================
# Podcast Agent — Transcription
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Handles audio transcription via two modes:
#   - Groq API (fast, cloud-based, requires internet)
#   - OpenAI Whisper (offline, runs locally)
#
# Supports three transcript types:
#   - Plain text (no timestamps)
#   - Segment level (timestamped by phrase)
#   - Word level (timestamped by individual word)
#
# Output is saved to the active episode's transcripts
# subfolder, referenced from output/metadata.json.
# ============================================================

import json
import os
import sys
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import INPUT_FOLDER, GROQ_API_KEY, PC_TRANSCRIPTS_FOLDER
from scripts.utils import format_time, load_metadata
# Import chunker using direct path since both files are in scripts/
import importlib.util, os as _os
_chunker_path = _os.path.join(_os.path.dirname(__file__), "chunker.py")
_spec = importlib.util.spec_from_file_location("chunker", _chunker_path)
_chunker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_chunker)

split_audio             = _chunker.split_audio
save_checkpoint         = _chunker.save_checkpoint
load_checkpoint         = _chunker.load_checkpoint
clear_checkpoint        = _chunker.clear_checkpoint
checkpoint_matches      = _chunker.checkpoint_matches
handle_stale_checkpoint = _chunker.handle_stale_checkpoint
stitch_transcripts      = _chunker.stitch_transcripts


# ============================================================
# AUDIO PICKER
# Scans the input/ folder for supported audio formats.
# If only one file exists it's selected automatically.
# If multiple exist, the user picks one or selects most recent.
# ============================================================

def pick_audio(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Uses config["audio_filename"] if specified
    #   - Falls back to most recently downloaded file in input/
    #   - Never prompts
    # When called interactively (config=None):
    #   - Lists files in input/ for quick selection
    #   - Offers option to provide a custom path to any file
    #     on the computer instead
    # ============================================================
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith(('.mp3', '.wav', '.m4a'))]

    # ---- Pipeline mode ----
    if config is not None:
        specified = config.get("audio_filename")
        if specified and specified in files:
            print(f"Using audio file: {specified}")
            return specified, INPUT_FOLDER
        chosen = max(files, key=lambda f: os.path.getmtime(os.path.join(INPUT_FOLDER, f))) if files else None
        if chosen:
            print(f"Using most recent audio file: {chosen}")
            return chosen, INPUT_FOLDER
        print("⚠️  No audio file found in input folder.")
        return None, None

    # ---- Interactive mode ----
    print("\nAudio source:")
    print("  1. Choose from input/ folder")
    print("  2. Provide a custom file path")
    source_choice = input("Enter 1 or 2: ").strip()

    if source_choice == "2":
        # ---- Custom file path ----
        custom_path = input("\nPaste the full file path: ").strip().strip('"')
        if not os.path.exists(custom_path):
            print(f"⚠️  File not found: {custom_path}")
            return None, None
        if not custom_path.endswith(('.mp3', '.wav', '.m4a')):
            print("⚠️  Unsupported file type. Please use .mp3, .wav or .m4a")
            return None, None
        print(f"Using: {custom_path}")
        # Return filename and its folder separately
        return os.path.basename(custom_path), os.path.dirname(custom_path)

    # ---- input/ folder selection ----
    if not files:
        print("⚠️  No audio file found in input folder. Please fetch an episode first.")
        return None, None

    if len(files) == 1:
        return files[0], INPUT_FOLDER

    print("\nMultiple audio files found:")
    for i, f in enumerate(files):
        print(f"  {i + 1}. {f}")
    print("  0. Use most recently downloaded")
    choice = input("Enter number: ").strip()

    if choice == "0":
        return max(files, key=lambda f: os.path.getmtime(os.path.join(INPUT_FOLDER, f))), INPUT_FOLDER
    return files[int(choice) - 1], INPUT_FOLDER

# ============================================================
# TIMESTAMP FORMATTERS
# Converts raw float seconds from Whisper/Groq into
# human-readable HH:MM:SS format for transcript output.
# ============================================================

def format_timestamp(seconds):
    # Converts seconds (float) to HH:MM:SS string
    seconds = float(seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"

def format_segments(segments):
    # Formats each segment as [start - end] text
    # Used for segment-level timestamped transcripts
    lines = []
    for seg in segments:
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"[{start} - {end}] {text}")
    return "\n".join(lines)

def format_words(words):
    # Formats each word with its start timestamp inline
    # Used for word-level timestamped transcripts
    lines = []
    for word in words:
        timestamp = format_timestamp(word["start"])
        lines.append(f"[{timestamp}] {word['word'].strip()}")
    return " ".join(lines)

# ============================================================
# OFFLINE TRANSCRIPTION (WHISPER)
# Runs OpenAI Whisper locally — no internet required.
# Uses the 'small' model for a balance of speed and accuracy.
# Supports all three transcript types via Whisper's built-in
# word_timestamps feature.
# ============================================================

def transcribe_offline(audio_path, transcript_type):
    try:
        import whisper
        print("Loading Whisper small model...")

        if transcript_type == "words":
            # word_timestamps=True returns per-word timing in segments
            model = whisper.load_model("small")
            result = model.transcribe(audio_path, word_timestamps=True)
            all_words = []
            for seg in result["segments"]:
                all_words.extend(seg.get("words", []))
            return format_words(all_words)

        elif transcript_type == "segments":
            # Standard transcribe returns segment-level timing
            model = whisper.load_model("small")
            result = model.transcribe(audio_path)
            return format_segments(result["segments"])

        else:
            # Plain text — just return the full transcript string
            model = whisper.load_model("small")
            result = model.transcribe(audio_path)
            return result["text"]

    except FileNotFoundError:
        print("⚠️  Audio file not found. Make sure the file exists in the input folder.")
        return None
    except Exception as e:
        print(f"⚠️  Offline transcription failed: {e}")
        print("   Try checking that Whisper is installed correctly (pip install openai-whisper)")
        return None

# ============================================================
# GROQ TRANSCRIPTION
# Sends audio to Groq's cloud Whisper API for fast processing.
# Audio is compressed to 64kbps mono via ffmpeg before upload
# to stay within Groq's 25MB file size limit.
# Falls back to offline mode automatically if file is too large
# or if the Groq API call fails with a size error.
# ============================================================

def transcribe_groq(audio_path, transcript_type):
    import subprocess
    from groq import Groq

    # ---- Compression ----
    try:
        print("Compressing audio for upload...")
        compressed_path = audio_path.replace(".mp3", "_compressed.mp3")
        result = subprocess.run([
            "ffmpeg", "-y", "-i", audio_path,
            "-b:a", "64k",   # 64kbps — sufficient for speech
            "-ac", "1",       # Mono — reduces file size further
            compressed_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode != 0:
            print("⚠️  Audio compression failed. Make sure ffmpeg is installed and added to PATH.")
            return None

    except FileNotFoundError:
        print("⚠️  ffmpeg not found. Please install ffmpeg and add it to your system PATH.")
        print("   Run 'python launch.py --setup' for installation guidance.")
        return None

    # ---- Size check ----
    file_size = os.path.getsize(compressed_path) / (1024 * 1024)
    print(f"Compressed size: {round(file_size, 2)}MB")

    if file_size > 25:
        # Still too large after compression — fall back to offline
        print("⚠️  File still too large for Groq after compression.")
        print("   Switching to offline Whisper — this may take significantly longer.")
        os.remove(compressed_path)
        return transcribe_offline(audio_path, transcript_type), "file_too_large"

    # ---- Groq API call ----
    try:
        client = Groq(api_key=GROQ_API_KEY)

        if transcript_type == "words":
            # Request word-level granularity from Groq
            with open(compressed_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            os.remove(compressed_path)
            return format_words(result.words)

        elif transcript_type == "segments":
            # Request segment-level granularity from Groq
            with open(compressed_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            os.remove(compressed_path)
            return format_segments(result.segments)

        else:
            # Plain text — simplest response format
            with open(compressed_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    file=f,
                    model="whisper-large-v3",
                    response_format="text"
                )
            os.remove(compressed_path)
            return result

    except Exception as e:
        # Handle specific Groq error codes with clear guidance
        if "401" in str(e) or "invalid_api_key" in str(e):
            print("⚠️  Invalid Groq API key. Run 'python launch.py --setup' to update it.")
        elif "429" in str(e):
            print("⚠️  Groq rate limit reached. Wait a moment and try again.")
        elif "413" in str(e):
            # File too large despite compression — fall back to offline
            print("⚠️  File too large for Groq.")
            print("   Switching to offline Whisper — this may take significantly longer.")
            if os.path.exists(compressed_path):
                os.remove(compressed_path)
            return transcribe_offline(audio_path, transcript_type), "file_too_large"
        else:
            print(f"⚠️  Groq transcription failed: {e}")
            print("   Check your internet connection or switch to offline mode.")

        # Clean up compressed file on any error
        if os.path.exists(compressed_path):
            os.remove(compressed_path)
        return None

# ============================================================
# MAIN
# Entry point called by main.py.
# Orchestrates the full transcription flow:
#   1. Load episode paths from metadata
#   2. Pick audio file from input/ folder
#   3. Choose transcription mode (Groq or Whisper)
#   4. Choose transcript type (plain, segments, words)
#   5. Run transcription and save to episode subfolder
# ============================================================

# ============================================================
# CHECKPOINT-AWARE TRANSCRIPTION
# Wraps the Groq and Whisper transcribers to add chunk-level
# progress saving. Called by transcribe() when the audio
# file is longer than one chunk (5 minutes).
#
# Flow:
#   1. Check for existing checkpoint — resume or start fresh
#   2. Split audio into 5-minute chunks via ffmpeg
#   3. Transcribe each chunk, saving progress after each one
#   4. Stitch all results into a single transcript
#   5. Clean up checkpoint and chunk files on success
# ============================================================

def transcribe_with_checkpoint(audio_path, transcript_type, mode, config=None):
    """
    Transcribes audio in 5-minute chunks with checkpoint saving.
    Resumes from the last completed chunk if a matching
    checkpoint exists.

    Args:
        audio_path      (str)  : Full path to the audio file.
        transcript_type (str)  : "plain", "segments" or "words".
        mode            (str)  : "groq" or "offline".
        config          (dict) : Optional pipeline config.

    Returns:
        str: Full stitched transcript, or None on failure.
    """

    # ---- Step 1: Check for existing checkpoint ----
    checkpoint   = load_checkpoint()
    resume_index = 0          # Which chunk to start from
    transcripts  = []         # Accumulated chunk results
    chunks       = None       # Will hold chunk file paths

    if checkpoint:
        if checkpoint_matches(checkpoint, audio_path, transcript_type, mode):
            # ---- Resume from last completed chunk ----
            completed    = checkpoint.get("completed", [])
            resume_index = len(completed)
            transcripts  = checkpoint.get("transcripts", [])
            chunks       = checkpoint.get("chunks", [])

            print(f"\n🔄 Resuming transcription from chunk {resume_index + 1}...")
            print(f"   ({resume_index} of {len(chunks)} chunk(s) already done)")

        else:
            # ---- Stale checkpoint — different job ----
            # Prompt user before discarding or proceeding
            should_proceed = handle_stale_checkpoint(checkpoint)
            if not should_proceed:
                return None
            # Checkpoint cleared — fall through to fresh start

    # ---- Step 2: Split audio into chunks (if not resuming) ----
    if not chunks:
        chunks = split_audio(audio_path, chunk_seconds=300)
        if not chunks:
            return None

        # Initialise checkpoint with job identity and chunk list
        save_checkpoint({
            "audio_path":      audio_path,
            "transcript_type": transcript_type,
            "mode":            mode,
            "total_chunks":    len(chunks),
            "completed":       [],
            "transcripts":     [],
            "chunks":          chunks,
        })

    total_chunks = len(chunks)
    print(f"\n📦 Transcribing {total_chunks} chunk(s)...")

    # ---- Step 3: Transcribe each chunk ----
    for i in range(resume_index, total_chunks):
        chunk_path = chunks[i]
        print(f"\n  Chunk {i + 1} of {total_chunks}: {os.path.basename(chunk_path)}")

        # ---- Transcribe this chunk ----
        if mode == "groq":
            # Use Groq for this chunk — returns string or tuple on fallback
            chunk_result = transcribe_groq(chunk_path, transcript_type)

            if isinstance(chunk_result, tuple):
                # Groq fell back to offline for this chunk
                chunk_transcript, fallback_reason = chunk_result
                print(f"   ⚡ Groq fallback on chunk {i + 1}: {fallback_reason}")
                if config is not None:
                    config["groq_fallback_triggered"] = True
                    config["groq_fallback_reason"]    = fallback_reason
            elif chunk_result is None:
                # Groq failed entirely — fall back to offline
                print(f"   ⚠️  Groq failed on chunk {i + 1}. Falling back to offline Whisper...")
                chunk_transcript = transcribe_offline(chunk_path, transcript_type)
                if config is not None:
                    config["groq_fallback_triggered"] = True
                    config["groq_fallback_reason"]    = "groq_api_failure"
            else:
                chunk_transcript = chunk_result

        else:
            # Use offline Whisper for this chunk
            chunk_transcript = transcribe_offline(chunk_path, transcript_type)

        if not chunk_transcript:
            print(f"   ⚠️  Chunk {i + 1} produced no output. Skipping.")
            chunk_transcript = ""

        # ---- Save progress after each chunk ----
        transcripts.append(chunk_transcript)

        save_checkpoint({
            "audio_path":      audio_path,
            "transcript_type": transcript_type,
            "mode":            mode,
            "total_chunks":    total_chunks,
            "completed":       list(range(i + 1)),
            "transcripts":     transcripts,
            "chunks":          chunks,
        })

        print(f"   ✅ Chunk {i + 1} complete — progress saved.")

    # ---- Step 4: Stitch all chunk transcripts ----
    print(f"\nStitching {total_chunks} chunk(s) into final transcript...")
    final_transcript = stitch_transcripts(transcripts, transcript_type, chunk_seconds=300)

    # ---- Step 5: Clean up checkpoint and chunk files ----
    clear_checkpoint()
    print("✅ Transcription complete. Checkpoint cleared.")

    return final_transcript

def transcribe(config=None):
    # ============================================================
    # When called from the pipeline (config provided):
    #   - Transcription mode pulled from config["transcribe_mode"]
    #     ("groq" or "offline")
    #   - Transcript type pulled from config["transcript_type"]
    #     ("plain", "segments" or "words")
    #   - No prompts at any decision point
    #   - Returns output path on success, None on failure
    # When called interactively (config=None):
    #   - Original behaviour — prompts for mode and type
    # ============================================================

    # ---- PC upload — skip metadata entirely ----
    # PC uploads save to PC_TRANSCRIPTS_FOLDER, not episode subfolders
    # metadata.json is irrelevant and may point to a previous RSS episode
    if config is not None and config.get("audio_source") == "pc":
        episode_paths = None
    else:
        # RSS episode — load episode subfolder paths from metadata
        metadata = load_metadata()
        if not metadata:
            return None
        episode_paths = metadata["episode_paths"]

    result = pick_audio(config)
    if not result or not result[0]:
        return None
    chosen, audio_folder = result

    audio_path = os.path.join(audio_folder, chosen)
    print(f"\nTranscribing: {chosen}")

    # ---- Mode selection ----
    if config is not None:
        # Pipeline mode — read from config, no prompt
        mode = "1" if config.get("transcribe_mode", "groq") == "groq" else "2"
    else:
        print("\nTranscription mode:")
        print("  1. Fast (Groq API — requires internet)")
        print("  2. Offline (Whisper small — no internet needed)")
        mode = input("Enter 1 or 2: ").strip()

    # ---- Transcript type selection ----
    if config is not None:
        # Pipeline mode — read from config, default to segments
        type_map = {"plain": "1", "segments": "2", "words": "3"}
        type_choice = type_map.get(config.get("transcript_type", "segments"), "2")
    else:
        print("\nTranscript type:")
        print("  1. Plain text (no timestamps)")
        print("  2. Segment level (timestamped by phrase)")
        print("  3. Word level (timestamped by word)")
        type_choice = input("Enter 1, 2 or 3: ").strip()

    # Map user choice to internal type string
    transcript_type = {
        "1": "plain",
        "2": "segments",
        "3": "words"
    }.get(type_choice, "plain")

    # Suffix appended to filename to distinguish transcript types
    type_suffix = {
        "plain":    "",
        "segments": "_segments",
        "words":    "_words"
    }[transcript_type]

    start = time.time()

    # ---- Determine transcription strategy ----
    # Files longer than 5 minutes use checkpoint-aware chunked
    # transcription. Shorter files transcribe in one pass as before.
    try:
        import subprocess as _sp
        dur_result = _sp.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True
        )
        duration_seconds = float(dur_result.stdout.strip())
    except Exception:
        # If duration check fails, default to chunked to be safe
        duration_seconds = 999

    use_chunked = duration_seconds > 300  # Chunk anything over 5 minutes

    if use_chunked:
        # ---- Chunked transcription with checkpoint ----
        print(f"\n⏱️  Audio is longer than 5 minutes — using chunked transcription.")
        print("   Progress will be saved after each chunk.")
        mode_str  = "groq" if mode == "1" else "offline"
        transcript = transcribe_with_checkpoint(
            audio_path, transcript_type, mode_str, config
        )

    elif mode == "1":
        # ---- Single-pass Groq transcription ----
        print("\nSending to Groq...")
        groq_result = transcribe_groq(audio_path, transcript_type)

        # transcribe_groq() returns a tuple (transcript, reason)
        # when it falls back to offline internally
        if isinstance(groq_result, tuple):
            # Groq fell back internally — unpack reason
            transcript, fallback_reason = groq_result
            print(f"\n⚠️  Groq fallback triggered: {fallback_reason}")
            print("   Transcription is running offline — this may take significantly longer than expected.")
            if config is not None:
                config["groq_fallback_triggered"] = True
                config["groq_fallback_reason"]    = fallback_reason

        elif groq_result is None and config is not None:
            # Groq failed entirely — fall back to offline
            print("⚠️  Groq transcription failed. Falling back to offline Whisper...")
            print("   This may take significantly longer than expected.")
            config["groq_fallback_triggered"] = True
            config["groq_fallback_reason"]    = "groq_api_failure"
            transcript = transcribe_offline(audio_path, transcript_type)

        else:
            # Groq succeeded — plain string returned
            transcript = groq_result

    else:
        # ---- Single-pass offline Whisper transcription ----
        transcript = transcribe_offline(audio_path, transcript_type)

    if not transcript:
        print("⚠️  Transcription produced no output. Please try again.")
        return None

    elapsed = round(time.time() - start, 2)
    print(f"Transcription completed in {format_time(elapsed)}")

    # ---- Determine save folder and clean filename ----
    if config is not None and config.get("audio_source") == "pc":
        # PC upload — save to dedicated pc_transcripts folder
        # Strip _temp_ prefix that may have been added during file handling
        transcript_folder = PC_TRANSCRIPTS_FOLDER
        os.makedirs(transcript_folder, exist_ok=True)
        clean_name = os.path.splitext(chosen)[0].replace("_temp_", "")
        filename   = clean_name + f"{type_suffix}.txt"
    else:
        # RSS episode — save to episode subfolder from metadata
        transcript_folder = episode_paths["transcripts"]
        clean_name = os.path.splitext(chosen)[0]
        filename   = clean_name + f"{type_suffix}.txt"

    output_path = os.path.join(transcript_folder, filename)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(transcript)

    print(f"Transcript saved to: {output_path}")
    return output_path