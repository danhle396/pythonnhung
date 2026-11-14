from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
EXPERIMENTS_DIR = ML_DIR / "experiments"
REPO_DIR = ML_DIR.parent
FIRMWARE_SRC = REPO_DIR / "firmware" / "src"
FIRMWARE_TESTS = REPO_DIR / "firmware" / "tests"

STATION = {"lat": 15.975, "lon": 108.253, "alt_m": 8.0, "tz": "Asia/Ho_Chi_Minh"}

SEED = 42
