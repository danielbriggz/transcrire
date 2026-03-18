# ============================================================
# Podcast Agent — Cleanup Utility
# Developer: Daniel "Briggz" Adisa
# ============================================================
# Standalone utility script that clears all files from the
# input/ and output/ folders.
#
# Preserves the folder structure itself — only files are
# deleted, not the folders.
#
# Run independently at any time:
#   python cleanup.py
# ============================================================

import os
import shutil

# ============================================================
# FOLDERS TO CLEAN
# input/  — downloaded audio files
# output/ — all episode subfolders, metadata, history,
#            new_episodes.json and any other generated files
# ============================================================

CLEAN_TARGETS = [
    "input",
    "output",
]

# ============================================================
# ROOT-LEVEL FILES TO DELETE
# State files that live in the project root and track
# episode history, active metadata and transcription
# checkpoints. Cleared alongside the output folders so
# the program starts completely fresh.
# ============================================================
CLEAN_FILES = [
    "history.json",
    "output/metadata.json",
    "output/new_episodes.json",
    "output/transcription_checkpoint.json",
]

def delete_folder_contents(folder):
    """
    Deletes all files and subfolders inside the given folder
    without deleting the folder itself.

    Args:
        folder (str): Path to the folder to clean.
    """
    if not os.path.exists(folder):
        print(f"⚠️  Folder not found, skipping: {folder}")
        return

    deleted_files   = 0
    deleted_folders = 0

    for item in os.listdir(folder):
        item_path = os.path.join(folder, item)

        try:
            if os.path.isfile(item_path) or os.path.islink(item_path):
                # Delete individual files and symlinks
                os.remove(item_path)
                print(f"  🗑️  Deleted file:   {item_path}")
                deleted_files += 1

            elif os.path.isdir(item_path):
                # Delete subfolders and all their contents recursively
                shutil.rmtree(item_path)
                print(f"  🗑️  Deleted folder: {item_path}")
                deleted_folders += 1

        except Exception as e:
            print(f"  ⚠️  Could not delete {item_path}: {e}")

    return deleted_files, deleted_folders

def cleanup():
    print("\n" + "=" * 40)
    print("     🧹  TRANSCRIRE — CLEANUP")
    print("=" * 40)
    print("\nThis will delete ALL files in:")
    for folder in CLEAN_TARGETS:
        print(f"  → {folder}/")

    print("\n⚠️  This action cannot be undone.")
    confirm = input("\nAre you sure? (yes/n): ").strip().lower()

    # Require full "yes" to prevent accidental deletion
    if confirm != "yes":
        print("\nCleanup cancelled.")
        return

    print("\nCleaning up...\n")

    total_files   = 0
    total_folders = 0

    # ---- Delete individual root-level files ----
    for filepath in CLEAN_FILES:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"  🗑️  Deleted file:   {filepath}")
                total_files += 1
            except Exception as e:
                print(f"  ⚠️  Could not delete {filepath}: {e}")

    # ---- Delete folder contents ----
    for folder in CLEAN_TARGETS:
        print(f"Cleaning {folder}/...")
        result = delete_folder_contents(folder)
        if result:
            files, folders = result
            total_files   += files
            total_folders += folders

    # ---- Summary ----
    print("\n" + "=" * 40)
    print("     ✅  CLEANUP COMPLETE")
    print("=" * 40)
    print(f"\n  Files deleted:   {total_files}")
    print(f"  Folders deleted: {total_folders}")
    print("\nAll folders have been preserved and are ready for a new episode.")

cleanup()