# ============================================================
# Transcrire — Audio Chunker + Checkpoint Manager
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Handles splitting audio into fixed-length chunks via ffmpeg,
# saving transcription progress to a checkpoint file after
# each chunk, and stitching results together on completion.
#
# Used by transcribe.py to enable resume-on-failure for
# long audio files.
#
# Checkpoint file: output/transcription_checkpoint.json
# Chunks folder:   output/chunks/
# ============================================================

import os
import json
import subprocess
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

CHECKPOINT_PATH = "output/transcription_checkpoint.json"
CHUNKS_FOLDER   = "output/chunks"

# ============================================================
# CHECKPOINT MANAGEMENT
# Saves and loads transcription progress so interrupted
# runs can resume from the last completed chunk.
# ============================================================

def save_checkpoint(data):
    """
    Saves current transcription progress to checkpoint file.

    Args:
        data (dict): Checkpoint state including completed
                     chunk indices and their transcripts.
    """
    os.makedirs(os.path.dirname(CHECKPOINT_PATH), exist_ok=True)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_checkpoint():
    """
    Loads an existing checkpoint file if present.

    Returns:
        dict: Checkpoint state, or None if no checkpoint exists.
    """
    if not os.path.exists(CHECKPOINT_PATH):
        return None
    try:
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def clear_checkpoint():
    """
    Removes checkpoint file and chunk folder after a
    successful transcription run.
    """
    # Remove checkpoint file
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        print("🗑️  Checkpoint cleared.")

    # Remove all chunk files
    if os.path.exists(CHUNKS_FOLDER):
        for f in os.listdir(CHUNKS_FOLDER):
            try:
                os.remove(os.path.join(CHUNKS_FOLDER, f))
            except Exception:
                pass
        try:
            os.rmdir(CHUNKS_FOLDER)
        except Exception:
            pass

def checkpoint_matches(checkpoint, audio_path, transcript_type, mode):
    """
    Checks whether a loaded checkpoint matches the current
    transcription job. Prevents resuming the wrong job.

    Returns:
        bool: True if checkpoint is for the same audio file,
              type and mode.
    """
    return (
        checkpoint.get("audio_path")      == audio_path and
        checkpoint.get("transcript_type") == transcript_type and
        checkpoint.get("mode")            == mode
    )

def handle_stale_checkpoint(checkpoint):
    # ============================================================
    # STALE CHECKPOINT HANDLER
    # Called when a checkpoint exists but doesn't match the
    # current transcription job — different audio file, type
    # or mode. Gives the user a clear choice before proceeding.
    #
    # Options:
    #   D — Delete stale chunks and start fresh
    #   K — Keep chunks on disk and start fresh anyway
    #   C — Cancel the current run entirely
    # ============================================================

    stale_audio = os.path.basename(checkpoint.get("audio_path", "unknown"))
    completed   = len(checkpoint.get("completed", []))
    total       = checkpoint.get("total_chunks", "?")

    print(f"\n⚠️  Found an incomplete transcription from a previous run:")
    print(f"   File     : {stale_audio}")
    print(f"   Progress : {completed} of {total} chunk(s) completed")
    print(f"\n   This doesn't match the current audio file.")
    print(f"\n   What would you like to do?")
    print(f"   D — Delete stale chunks and start fresh")
    print(f"   K — Keep chunks on disk and start fresh")
    print(f"   C — Cancel")

    while True:
        choice = input("\n   Enter D, K or C: ").strip().upper()

        if choice == "D":
            # ---- Delete stale chunks and checkpoint ----
            clear_checkpoint()
            print("✅ Stale chunks deleted. Starting fresh.")
            return True  # Proceed with fresh run

        elif choice == "K":
            # ---- Keep chunks but ignore them ----
            print("⚠️  Stale chunks kept. Starting fresh without resuming.")
            return True  # Proceed with fresh run

        elif choice == "C":
            # ---- Cancel ----
            print("Run cancelled.")
            return False  # Abort transcription

        else:
            print("⚠️  Invalid choice. Please enter D, K or C.")

# ============================================================
# AUDIO SPLITTER
# Splits a single audio file into fixed-length chunks using
# ffmpeg. Default chunk length is 5 minutes (300 seconds).
# Returns list of chunk file paths in order.
# ============================================================

def split_audio(audio_path, chunk_seconds=300):
    """
    Splits audio into fixed-length chunks via ffmpeg.

    Args:
        audio_path   (str): Full path to the audio file.
        chunk_seconds (int): Duration of each chunk in seconds.
                             Default is 300 (5 minutes).

    Returns:
        list[str]: Ordered list of chunk file paths,
                   or None if splitting fails.
    """
    os.makedirs(CHUNKS_FOLDER, exist_ok=True)

    # Build output pattern — chunks named chunk_000.mp3, chunk_001.mp3 etc.
    base_name    = os.path.splitext(os.path.basename(audio_path))[0]
    chunk_pattern = os.path.join(CHUNKS_FOLDER, f"{base_name}_chunk_%03d.mp3")

    print(f"\nSplitting audio into {chunk_seconds // 60}-minute chunks...")

    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", audio_path,
            "-f", "segment",
            "-segment_time", str(chunk_seconds),
            "-c", "copy",
            chunk_pattern
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if result.returncode != 0:
            print("⚠️  ffmpeg failed to split audio.")
            print("   Make sure ffmpeg is installed and added to PATH.")
            return None

    except FileNotFoundError:
        print("⚠️  ffmpeg not found.")
        print("   Run 'python launch.py --setup' for installation guidance.")
        return None

    # Collect all generated chunk files in sorted order
    chunks = sorted([
        os.path.join(CHUNKS_FOLDER, f)
        for f in os.listdir(CHUNKS_FOLDER)
        if f.startswith(base_name) and f.endswith(".mp3")
    ])

    if not chunks:
        print("⚠️  No chunks were created. Check the audio file.")
        return None

    print(f"✅ Audio split into {len(chunks)} chunk(s).")
    return chunks

# ============================================================
# TRANSCRIPT STITCHER
# Joins completed chunk transcripts into a single output.
# Handles plain text, segment-level and word-level formats.
# Segment timestamps are offset per chunk to stay accurate.
# ============================================================

def stitch_transcripts(transcripts, transcript_type, chunk_seconds=300):
    """
    Joins chunk transcripts into a single coherent transcript.
    Adjusts timestamps for segment and word-level transcripts
    based on each chunk's position in the original audio.

    Args:
        transcripts    (list[str]): Ordered chunk transcripts.
        transcript_type (str)     : "plain", "segments" or "words".
        chunk_seconds   (int)     : Duration per chunk for offset calc.

    Returns:
        str: Stitched final transcript.
    """
    if transcript_type == "plain":
        # Plain text — just join with a space
        return " ".join(t.strip() for t in transcripts if t)

    elif transcript_type == "segments":
        # Segment format: [HH:MM:SS - HH:MM:SS] text
        # Each chunk's timestamps need to be offset by chunk index
        stitched_lines = []
        for chunk_index, transcript in enumerate(transcripts):
            if not transcript:
                continue
            offset_seconds = chunk_index * chunk_seconds
            for line in transcript.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Apply time offset to both start and end timestamps
                adjusted = _offset_segment_line(line, offset_seconds)
                stitched_lines.append(adjusted)
        return "\n".join(stitched_lines)

    elif transcript_type == "words":
        # Word format: [HH:MM:SS] word [HH:MM:SS] word ...
        # Offset each timestamp by chunk position
        stitched_words = []
        for chunk_index, transcript in enumerate(transcripts):
            if not transcript:
                continue
            offset_seconds = chunk_index * chunk_seconds
            adjusted = _offset_word_transcript(transcript, offset_seconds)
            stitched_words.append(adjusted)
        return " ".join(stitched_words)

    return " ".join(t.strip() for t in transcripts if t)

def _offset_segment_line(line, offset_seconds):
    """
    Adjusts timestamps in a single segment line by offset_seconds.
    Format: [HH:MM:SS - HH:MM:SS] text

    Returns the adjusted line, or the original if parsing fails.
    """
    import re
    pattern = r"\[(\d{2}:\d{2}:\d{2}) - (\d{2}:\d{2}:\d{2})\](.*)"
    match   = re.match(pattern, line)

    if not match:
        return line

    start_str, end_str, text = match.groups()
    start_adj = _add_offset_to_timestamp(start_str, offset_seconds)
    end_adj   = _add_offset_to_timestamp(end_str, offset_seconds)
    return f"[{start_adj} - {end_adj}]{text}"

def _offset_word_transcript(transcript, offset_seconds):
    """
    Adjusts all timestamps in a word-level transcript by offset_seconds.
    Format: [HH:MM:SS] word [HH:MM:SS] word ...

    Returns adjusted transcript string.
    """
    import re
    def replace_ts(match):
        return "[" + _add_offset_to_timestamp(match.group(1), offset_seconds) + "]"
    return re.sub(r"\[(\d{2}:\d{2}:\d{2})\]", replace_ts, transcript)

def _add_offset_to_timestamp(ts_str, offset_seconds):
    """
    Adds offset_seconds to a HH:MM:SS timestamp string.

    Returns adjusted HH:MM:SS string.
    """
    h, m, s   = map(int, ts_str.split(":"))
    total_secs = h * 3600 + m * 60 + s + offset_seconds
    new_h      = total_secs // 3600
    new_m      = (total_secs % 3600) // 60
    new_s      = total_secs % 60
    return f"{new_h:02}:{new_m:02}:{new_s:02}"