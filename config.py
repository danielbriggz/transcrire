# ============================================================
# Transcrire — Configuration
# Developer: Daniel "Briggz" Adisa
# ============================================================
# API keys are loaded from a .env file in the project root.
# Never store actual keys in this file — they will be
# exposed if committed to GitHub.
# ============================================================

import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()

# ============================================================
# API KEYS
# Set in .env file — never hardcoded here
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# ============================================================
# FOLDER PATHS
# ============================================================
INPUT_FOLDER          = "input"
TRANSCRIPT_FOLDER     = "output/transcripts"
CAPTIONS_FOLDER       = "output/captions"
IMAGES_FOLDER         = "output/images"
PC_TRANSCRIPTS_FOLDER = os.path.join("output", "pc_transcripts") # Transcripts from PC audio uploads