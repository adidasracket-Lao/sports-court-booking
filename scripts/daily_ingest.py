#!/usr/bin/env python3
"""Daily auto-ingest: pull booking receipts from Hermes image cache into the site repo."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_data import (  # noqa: E402
    extract_codes,
    extract_court,
    extract_date,
    extract_time,
)

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
MANUAL_CSV = ROOT / "場地租用資料.csv"
CACHE_DIR = Path.home() / ".hermes" / "image_cache"
STATE_FILE = Path.home() / "Library" / "Application Support" / "badminton-ingest" / "state.json"
LOG_FILE = Path.home() / "Library" / "Logs" / "badminton-ingest.log"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

RECEIPT_KEYWORDS = ("收據", "體育局", "使用時段", "租場者", "場區編號")


def extract_receipt_id(text: str) -> str:
    compact = text.replace(" ", "")
    match = re.search(r"[I1]DOB([A-Z0-9]{12,18})", compact)
    return f"IDOB{match.group(1)}" if match else ""


def looks_like_receipt(text: str) -> bool:
    return any(keyword in text for keyword in RECEIPT_KEYWORDS)


def parse_receipt(text: str) -> dict:
    codes = extract_codes(text)
    return {
        "receipt_id": extract_receipt_id(text),
        "date": extract_date(text),
        "time": extract_time(text),
        "court": extract_court(text),
        "renter_code": codes[0] if len(codes) > 0 else "",
        "extra_code": codes[1] if len(codes) > 1 else "",
    }


def field_count(parsed: dict) -> int:
    return sum(1 for key in ("date", "time", "court", "renter_code", "extra_code") if parsed.get(key))
