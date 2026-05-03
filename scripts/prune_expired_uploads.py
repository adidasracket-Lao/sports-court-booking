#!/usr/bin/env python3
"""Delete expired booking screenshots from uploads/ while keeping CSV/JSON records."""
import argparse
import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
MANUAL_CSV = ROOT / "場地租用資料.csv"
TZ = ZoneInfo("Asia/Macau")


def parse_end_datetime(value: str):
    value = (value or "").strip()
    if " " not in value or "~" not in value:
        return None
    date_part, time_part = value.split(" ", 1)
    end_time = time_part.split("~", 1)[1].strip()
    for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(f"{date_part} {end_time}", fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    return None


def load_expired_sources(now: datetime):
    expired = []
    if not MANUAL_CSV.exists():
        return expired
    with MANUAL_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = (row.get("source") or row.get("圖片") or "").strip()
            end_dt = parse_end_datetime(row.get("使用時間", ""))
            if source and end_dt and end_dt < now:
                expired.append((source, end_dt, row.get("使用時間", ""), row.get("場地編號", "")))
    return expired


def main():
    parser = argparse.ArgumentParser(description="Prune expired booking screenshots from uploads/.")
    parser.add_argument("--apply", action="store_true", help="actually delete files; default is dry-run")
    args = parser.parse_args()

    now = datetime.now(TZ)
    expired = load_expired_sources(now)
    deleted = []
    missing = []
    for source, end_dt, booking_time, court in expired:
        path = UPLOAD_DIR / source
        if path.exists() and path.is_file():
            if args.apply:
                path.unlink()
            deleted.append((source, booking_time, court))
        else:
            missing.append(source)

    action = "deleted" if args.apply else "would_delete"
    print(f"now={now.isoformat(timespec='seconds')}")
    print(f"expired_sources={len(expired)}")
    print(f"{action}={len(deleted)}")
    for source, booking_time, court in deleted:
        print(f"{action}: {source} | {booking_time} | {court}")
    print(f"already_missing={len(missing)}")


if __name__ == "__main__":
    main()
