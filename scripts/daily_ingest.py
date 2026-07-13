#!/usr/bin/env python3
"""Daily auto-ingest: pull booking receipts from Hermes image cache into the site repo."""
import argparse
import csv
import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime
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
    match = re.search(r"[I1TL]DOB([A-Z0-9]{12,18})", compact)
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


def notify(title: str, message: str) -> None:
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def git_sync(added: list) -> None:
    def run(*args, check=True):
        return subprocess.run(["git", "-C", str(ROOT), *args],
                              check=check, capture_output=True, text=True)

    # autostash tolerates unrelated dirty files (e.g. regenerated records.json)
    run("pull", "--rebase", "--autostash", "origin", "main")
    # add the whole uploads dir so files left behind by an earlier failed push get swept up
    run("add", str(UPLOAD_DIR), str(MANUAL_CSV))
    staged = run("diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return  # nothing to commit
    message = (f"Auto-ingest {datetime.now():%Y-%m-%d}: add {len(added)} booking records\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    run("commit", "-m", message)
    run("push", "origin", "main")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest booking receipts from Hermes cache.")
    parser.add_argument("--dry-run", action="store_true", help="report only; no writes")
    parser.add_argument("--bootstrap", action="store_true",
                        help="mark all current cache images as processed without ingesting")
    args = parser.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
    )
    log = logging.getLogger("ingest")

    if args.bootstrap:
        state = load_state()
        hashes = set(state.get("processed_hashes", []))
        count = 0
        for path in sorted(CACHE_DIR.iterdir()):
            if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file():
                digest = sha1_of(path)
                if digest not in hashes:
                    hashes.add(digest)
                    count += 1
        state["processed_hashes"] = sorted(hashes)
        save_state(state)
        log.info("bootstrap: marked %d cache images as processed", count)
        return 0

    try:
        report = ingest(dry_run=args.dry_run)
    except Exception:
        log.exception("ingest failed")
        notify("羽毛球場地入庫失敗", "OCR/檔案階段出錯，詳見 badminton-ingest.log")
        return 1

    log.info("added=%s incomplete=%s suspects=%s",
             report["added"], report["incomplete"], report["suspects"])

    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    # run even when added==[] so files left by an earlier failed push get committed
    try:
        git_sync(report["added"])
    except subprocess.CalledProcessError as error:
        log.error("git failed: %s\n%s", error, error.stderr)
        notify("羽毛球場地 push 失敗", "git 出錯，詳見 badminton-ingest.log")
        return 1

    parts = [f"新增 {len(report['added'])} 筆"]
    if report["incomplete"]:
        parts.append(f"{len(report['incomplete'])} 筆欄位不全需人手補")
    if report["suspects"]:
        parts.append(f"{len(report['suspects'])} 張疑似收據讀不到編號")
    notify("羽毛球場地更新", "，".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
