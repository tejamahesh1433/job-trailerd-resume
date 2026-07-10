import os
import json
from datetime import datetime

DATA_DIR = os.getenv("DATA_DIR", "data")
SCAN_STATUS_FILE = os.path.join(DATA_DIR, "last_scan.json")


def save_last_scan(platforms: list, query: str, result_count: int):
    data = {
        "timestamp": datetime.now().isoformat(),
        "platforms": platforms or [],
        "query": query,
        "result_count": result_count,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SCAN_STATUS_FILE, "w") as f:
        json.dump(data, f)


def get_last_scan():
    if os.path.exists(SCAN_STATUS_FILE):
        try:
            with open(SCAN_STATUS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None
