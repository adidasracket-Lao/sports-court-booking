# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A static GitHub Pages site that organizes badminton court booking records. Images of booking confirmations are OCR-processed to extract structured data (date, time, court, renter codes), then displayed in a filterable table with a name lookup.

## Architecture

The system has two distinct layers:

**Build-time (Python):** `scripts/generate_data.py` runs during CI to:
1. OCR every image in `uploads/` via the `tesseract` CLI (prefers `chi_tra+eng` if available)
2. Extract date, time, court number, and 4-digit renter codes from raw OCR text
3. Cross-reference codes with `取場人對照表.csv` (code → name mapping) and optionally override fields from the manual `場地租用資料.csv`
4. Write `data/records.json` — the single output consumed by the frontend

**Runtime (browser):** `app.js` fetches `data/records.json` and renders the table. It also supports local OCR preview via Tesseract.js (browser-side, no server needed). `background-sketch.js` drives the p5.js animated background.

## Data Files

| File | Format | Purpose |
|------|--------|---------|
| `uploads/*.jpg/png` | Images | Source booking screenshots |
| `取場人對照表.csv` | `後四碼,取場人` | Maps 4-digit codes to full names |
| `場地租用資料.csv` | Structured CSV | Manual overrides; matched to OCR output by date/time/court/code score |
| `data/records.json` | JSON | Generated output; consumed by frontend |

## Local Development

**Run the OCR pipeline manually (requires `tesseract` installed):**
```sh
python scripts/generate_data.py
```

**Install tesseract on macOS:**
```sh
brew install tesseract tesseract-lang
```

**Preview the site locally** — open `index.html` directly in a browser, or use any static server:
```sh
python -m http.server 8000
```

Note: `data/records.json` must exist before the frontend can display the official table. The local OCR preview in the upload section works without it.

## CI/CD

GitHub Actions (`.github/workflows/deploy-pages.yml`) triggers on every push to `main` and on a daily cron at 03:00 UTC (11:00 Macau time). The workflow:
1. Installs Python 3.12 + `tesseract-ocr` + `tesseract-ocr-chi-tra`
2. Runs `scripts/generate_data.py` to produce `data/records.json`
3. Deploys the entire repo root as a GitHub Pages artifact

## Key Matching Logic

When `場地租用資料.csv` has the same number of rows as images, the script matches them **by sorted order** (both sorted by datetime). Otherwise, it scores each manual row against parsed OCR fields and uses the match only if score ≥ 6 (time=4, renter_code=4, extra_code=4, court=3, date=2).

## Adding New Records

1. Drop images into `uploads/`
2. Optionally add rows to `場地租用資料.csv` or update `取場人對照表.csv`
3. Push to `main` — CI rebuilds and deploys automatically
