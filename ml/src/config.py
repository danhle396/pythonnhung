"""Hằng số dùng chung cho pipeline ML (vị trí trạm, đường dẫn)."""
from pathlib import Path

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"
MODELS_DIR = ML_DIR / "models"
EXPERIMENTS_DIR = ML_DIR / "experiments"
REPO_DIR = ML_DIR.parent
FIRMWARE_INCLUDE = REPO_DIR / "firmware" / "include"

# Trường ĐH CNTT & TT Việt – Hàn (VKU), 470 Trần Đại Nghĩa, Ngũ Hành Sơn, Đà Nẵng
STATION = {"lat": 15.975, "lon": 108.253, "alt_m": 8.0, "tz": "Asia/Ho_Chi_Minh"}

SEED = 42
