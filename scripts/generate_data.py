#!/usr/bin/env python3
import csv
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
NAME_MAP_CSV = ROOT / "取場人對照表.csv"
MANUAL_CSV = ROOT / "場地租用資料.csv"
OUTPUT_JSON = ROOT / "data" / "records.json"
TIMEZONE = "Asia/Macau"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class ManualRow:
    date: str
    time: str
    court: str
    renter_code: str
    extra_code: str
    renter_name: str
    extra_name: str


def normalize_code(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def pad_code(value: str) -> str:
    digits = normalize_code(value)
    if not digits:
        return ""
    return digits.zfill(4) if len(digits) < 4 else digits


def load_name_map() -> Dict[str, str]:
    name_map: Dict[str, str] = {}
    if not NAME_MAP_CSV.exists():
        return name_map

    with NAME_MAP_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            code = normalize_code(row.get("後四碼", ""))
            name = (row.get("取場人") or "").strip()
            if code and name:
                name_map[code] = name
    return name_map


def load_manual_rows() -> List[ManualRow]:
    rows: List[ManualRow] = []
    if not MANUAL_CSV.exists():
        return rows

    with MANUAL_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                ManualRow(
                    date=(row.get("使用時間", "").split(" ", 1)[0]).strip(),
                    time=(row.get("使用時間", "").split(" ", 1)[1]).strip()
                    if " " in row.get("使用時間", "")
                    else "",
                    court=(row.get("場地編號") or "").strip(),
                    renter_code=pad_code(row.get("租場者", "")),
                    extra_code=pad_code(row.get("額外取場者", "")),
                    renter_name=(row.get("租場者(姓名）") or "").strip(),
                    extra_name=(row.get("額外取場者（姓名）") or "").strip(),
                )
            )
    return rows


def available_tesseract_languages() -> List[str]:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    lines = [line.strip() for line in result.stdout.splitlines()]
    return [line for line in lines if line and not line.startswith("List of available")]


def ocr_image(image_path: Path, languages: List[str]) -> str:
    preferred = "eng"
    if "chi_tra" in languages and "eng" in languages:
        preferred = "chi_tra+eng"
    elif "chi_tra" in languages:
        preferred = "chi_tra"

    for psm in ("6", "11"):
        try:
            result = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", preferred, "--psm", psm],
                check=True,
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                return result.stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return ""


def extract_date(text: str) -> str:
    match = re.search(r"(20\d{2})[-/](\d{2})[-/](\d{2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}/{int(month)}/{int(day)}"


def extract_time(text: str) -> str:
    match = re.search(r"(\d{1,2}:\d{2})\s*[~\-]\s*(\d{1,2}:\d{2})", text)
    if not match:
        return ""
    return f"{match.group(1)}~{match.group(2)}"


def extract_court(text: str) -> str:
    patterns = [
        r"羽毛球\s*([0-9]+)\s*號場",
        r"球場\s*([0-9]+)\s*號場",
        r"場區編號[:：]?\s*羽毛球\s*([0-9]+)\s*號場",
        r"羽毛球([0-9]+)號場",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"羽毛球{match.group(1)}號場"

    for line in text.splitlines():
        if "號場" in line or "场" in line or "場" in line:
            digits = re.findall(r"([0-9]+)", line)
            if digits:
                return f"羽毛球{digits[-1]}號場"
    return ""


def extract_codes(text: str) -> List[str]:
    explicit_patterns = [
        r"租場者[^0-9]*(\d{3,4})",
        r"額外取場者[^0-9]*(\d{3,4})",
    ]
    found: List[str] = []
    for pattern in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            found.append(pad_code(match.group(1)))

    if len(found) >= 2:
        return found[:2]

    masked = re.findall(r"[*#]{2,}\s*0?(\d{3,4})", text)
    for code in masked:
        found.append(pad_code(code))
        if len(found) == 2:
            return found

    trailing = re.findall(r"\b(\d{3,4})\b", text)
    for code in trailing:
        padded = pad_code(code)
        if padded not in found:
            found.append(padded)
        if len(found) == 2:
            return found
    return found[:2]


def match_manual_row(parsed: dict, manual_rows: List[ManualRow]) -> Optional[ManualRow]:
    best_row: Optional[ManualRow] = None
    best_score = -1

    for row in manual_rows:
        score = 0
        if parsed.get("date") and parsed["date"] == row.date:
            score += 2
        if parsed.get("time") and parsed["time"] == row.time:
            score += 4
        if parsed.get("renter_code") and parsed["renter_code"] == row.renter_code:
            score += 4
        if parsed.get("extra_code") and parsed["extra_code"] == row.extra_code:
            score += 4
        if parsed.get("court") and parsed["court"] == row.court:
            score += 3

        if score > best_score:
            best_score = score
            best_row = row

    return best_row if best_score >= 6 else None


def manual_sort_key(row: ManualRow) -> tuple:
    try:
        dt = datetime.strptime(f"{row.date} {row.time.split('~', 1)[0]}", "%Y/%m/%d %H:%M")
        return (dt, row.court, row.renter_code, row.extra_code)
    except Exception:
        return (datetime.max, row.court, row.renter_code, row.extra_code)


def record_sort_key(record: dict) -> tuple:
    try:
        start_time = record["time"].split("~", 1)[0]
        dt = datetime.strptime(f'{record["date"]} {start_time}', "%Y/%m/%d %H:%M")
        return (dt, record["court"], record["sourceFile"])
    except Exception:
        return (datetime.max, record.get("court", ""), record.get("sourceFile", ""))


def build_records() -> dict:
    name_map = load_name_map()
    manual_rows = load_manual_rows()
    languages = available_tesseract_languages()
    parsed_images = []

    for image_path in sorted(UPLOAD_DIR.iterdir()):
        if image_path.suffix.lower() not in IMAGE_EXTENSIONS or not image_path.is_file():
            continue

        text = ocr_image(image_path, languages)
        codes = extract_codes(text)
        parsed = {
            "date": extract_date(text),
            "time": extract_time(text),
            "court": extract_court(text),
            "renter_code": codes[0] if len(codes) > 0 else "",
            "extra_code": codes[1] if len(codes) > 1 else "",
        }

        parsed_images.append(
            {
                "id": image_path.stem,
                "date": parsed["date"],
                "time": parsed["time"],
                "court": parsed["court"],
                "renterCode": parsed["renter_code"],
                "extraCode": parsed["extra_code"],
                "image": f"uploads/{image_path.name}",
                "sourceFile": image_path.name,
            }
        )

    records = []
    use_manual_by_order = bool(manual_rows) and len(manual_rows) == len(parsed_images)
    sorted_manual_rows = sorted(manual_rows, key=manual_sort_key)
    sorted_images = sorted(parsed_images, key=record_sort_key)

    for index, parsed in enumerate(sorted_images):
        matched = None
        if use_manual_by_order:
            matched = sorted_manual_rows[index]
        else:
            matched = match_manual_row(parsed, manual_rows)

        if matched:
            parsed["date"] = matched.date or parsed["date"]
            parsed["time"] = matched.time or parsed["time"]
            parsed["court"] = matched.court or parsed["court"]
            parsed["renterCode"] = matched.renter_code or parsed["renterCode"]
            parsed["extraCode"] = matched.extra_code or parsed["extraCode"]

        renter_name = name_map.get(normalize_code(parsed["renterCode"]), "")
        extra_name = name_map.get(normalize_code(parsed["extraCode"]), "")
        if matched:
            renter_name = renter_name or matched.renter_name
            extra_name = extra_name or matched.extra_name

        parsed["renterName"] = renter_name
        parsed["extraName"] = extra_name
        records.append(parsed)

    records.sort(key=record_sort_key)
    return {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "timezone": TIMEZONE,
        "records": records,
        "nameMap": name_map,
    }


def main() -> None:
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = build_records()
    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(payload['records'])} records to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
