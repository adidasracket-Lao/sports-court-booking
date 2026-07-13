#!/usr/bin/env python3
"""Daily auto-ingest: pull booking receipts from Hermes image cache into the site repo."""
import csv
import hashlib
import io
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_data import (  # noqa: E402
    available_tesseract_languages,
    extract_codes,
    extract_court,
    extract_date,
    extract_time,
    ocr_image,
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


_OCR_LANGS: list = []


def ocr_cache_image(path: Path) -> str:
    global _OCR_LANGS
    if not _OCR_LANGS:
        _OCR_LANGS = available_tesseract_languages()
    return ocr_image(path, _OCR_LANGS)


def sha1_of(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"processed_hashes": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def list_new_images(state: dict) -> list:
    processed = set(state.get("processed_hashes", []))
    new_images = []
    if not CACHE_DIR.exists():
        return new_images
    for path in sorted(CACHE_DIR.iterdir()):
        if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file():
            if sha1_of(path) not in processed:
                new_images.append(path)
    return new_images


def known_receipt_ids() -> set:
    ids = set()
    if not MANUAL_CSV.exists():
        return ids
    with MANUAL_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            source = (row.get("source") or "").strip()
            match = re.search(r"(IDOB[A-Z0-9]{12,18})", source)
            if match:
                ids.add(match.group(1))
    return ids


def make_filename(parsed: dict, suffix: str) -> str:
    year, month, day = parsed["date"].split("/")
    return f"{year}{int(month):02d}{int(day):02d}_{parsed['receipt_id']}{suffix}"


def csv_line(parsed: dict, filename: str) -> str:
    when = f"{parsed['date']} {parsed['time']}".strip()
    fields = [when, parsed.get("court", ""), parsed.get("renter_code", ""),
              parsed.get("extra_code", ""), "", "", filename]
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="").writerow(fields)
    return buffer.getvalue()


def append_csv_lines(lines: list) -> None:
    raw = MANUAL_CSV.read_bytes()
    if raw and not raw.endswith(b"\r\n"):
        raw += b"\r\n"
    payload = "".join(line + "\r\n" for line in lines).encode("utf-8")
    MANUAL_CSV.write_bytes(raw + payload)


def ingest(dry_run: bool) -> dict:
    state = load_state()
    report = {"added": [], "incomplete": [], "suspects": []}
    candidates: dict = {}  # receipt_id -> (parsed, path)
    new_hashes = []

    for path in list_new_images(state):
        text = ocr_cache_image(path)
        new_hashes.append(sha1_of(path))
        receipt_id = extract_receipt_id(text)
        if not receipt_id:
            if looks_like_receipt(text):
                report["suspects"].append(path.name)
            continue
        parsed = parse_receipt(text)
        current = candidates.get(receipt_id)
        if current is None or field_count(parsed) > field_count(current[0]):
            candidates[receipt_id] = (parsed, path)

    existing = known_receipt_ids()
    for receipt_id, (parsed, path) in sorted(candidates.items()):
        if receipt_id in existing:
            continue
        if not parsed["date"]:
            report["suspects"].append(path.name)
            continue
        filename = make_filename(parsed, path.suffix.lower())
        if not dry_run:
            shutil.copy2(path, UPLOAD_DIR / filename)
            append_csv_lines([csv_line(parsed, filename)])
        report["added"].append(filename)
        if field_count(parsed) < 5:
            report["incomplete"].append(filename)

    if not dry_run:
        state["processed_hashes"] = state.get("processed_hashes", []) + new_hashes
        save_state(state)
    return report
