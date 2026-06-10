"""Project settings — loaded from the .env file at the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")

CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
