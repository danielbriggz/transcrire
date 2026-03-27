# ============================================================
# Transcrire — Configuration
# ============================================================
# Single source of truth for all settings.
# Reads from .env automatically via pydantic-settings.
# All TRANSCRIRE_* environment variables set by Transcrire.cmd
# are picked up here via the env_prefix.
#
# In development (VS Code), no env vars need to be set —
# defaults resolve to the project root.
# ============================================================

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ---- API Keys ----
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # ---- Paths ----
    # Overridden by Transcrire.cmd via TRANSCRIRE_* env vars.
    # Defaults are relative to project root for development.
    app_data_dir: Path = Path.home() / "AppData" / "Roaming" / "Transcrire"
    input_folder: Path = Path("input")
    output_folder: Path = Path("output")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "TRANSCRIRE_",
        "case_sensitive": False,
    }

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite database file."""
        return self.app_data_dir / "transcrire.db"

    @property
    def fonts_dir(self) -> Path:
        """Absolute path to the fonts directory."""
        return Path(__file__).parent.parent / "assets" / "fonts"


# Single shared instance — import this everywhere.
# from transcrire.config import settings
settings = Settings()
