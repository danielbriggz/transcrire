# ============================================================
# Transcrire — Configuration
# Developer: Daniel "Briggz" Adisa
# ============================================================
# API keys are loaded from a .env file.
# When launched via Transcrire.cmd, the .env lives in AppData.
# When run from VS Code, the .env lives in the project root.
# Never store actual keys in this file.
# ============================================================

import os
from dotenv import load_dotenv

# ============================================================
# ENV FILE LOCATION
# TRANSCRIRE_APPDATA is set by Transcrire.cmd at launch.
# If not set, fall back to project root (VS Code / dev mode).
# ============================================================
APP_DIR = os.environ.get("TRANSCRIRE_APPDATA", os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(APP_DIR, ".env")

# Load .env from the correct location
load_dotenv(dotenv_path=ENV_PATH)

# ============================================================
# API KEYS
# Read from .env — never hardcoded here
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# ============================================================
# FOLDER PATHS
# When launched via .cmd, input/output point to Desktop.
# When run from VS Code, they point to the project root.
# ============================================================
INPUT_FOLDER  = os.environ.get("TRANSCRIRE_INPUT",  "input")
OUTPUT_BASE   = os.environ.get("TRANSCRIRE_OUTPUT", "output")

TRANSCRIPT_FOLDER     = os.path.join(OUTPUT_BASE, "transcripts")
CAPTIONS_FOLDER       = os.path.join(OUTPUT_BASE, "captions")
IMAGES_FOLDER         = os.path.join(OUTPUT_BASE, "images")
PC_TRANSCRIPTS_FOLDER = os.path.join(OUTPUT_BASE, "pc_transcripts")