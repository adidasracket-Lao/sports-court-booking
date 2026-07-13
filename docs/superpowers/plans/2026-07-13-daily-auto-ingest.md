# Daily Auto-Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天 10:30 自動把 Hermes 收到的場地收據圖入庫（OCR → CSV → push），11:00 CI 重建網站；以收據編號對位去重，消滅圖文錯位。

**Architecture:** 新增本機腳本 `scripts/daily_ingest.py`（掃 `~/.hermes/image_cache/` → OCR 過濾 → 以 IDOB 收據編號去重 → 複製改名到 `uploads/` → 追加 CSV → git push → macOS 通知），由 launchd 每日 10:30 觸發。同時修正 `scripts/generate_data.py` 的對位邏輯：只按 `source` 精確對檔名，score fallback 只適用於無 source 的舊資料行。

**Tech Stack:** Python 3.14（stdlib only）、tesseract CLI（chi_tra+eng）、unittest、launchd、osascript。

## Global Constraints

- 測試框架：stdlib `unittest`（本機無 pytest），跑法 `python3 -m unittest tests.test_xxx -v`
- CSV 檔 `場地租用資料.csv`：UTF-8 with BOM（utf-8-sig）、CRLF 行尾，欄位順序 `使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source`
- 日期格式與現有 CSV 一致：`2026/7/15 17:00~18:00`（月/日不補零）
- 新圖檔名：`{YYYYMMDD}_{收據編號}{原副檔名小寫}`，例 `20260715_IDOB260712073004WXI.jpg`
- 收據編號 regex 須容錯 OCR 誤讀（`1DOB` → `IDOB`）
- state 檔：`~/Library/Application Support/badminton-ingest/state.json`
- log 檔：`~/Library/Logs/badminton-ingest.log`
- commit message 結尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 所有路徑常數集中在模組頂部，方便測試 monkeypatch

---

### Task 1: 修正 generate_data.py 對位邏輯

**Files:**
- Modify: `scripts/generate_data.py:191-218`（match_manual_row）、`scripts/generate_data.py:290-303`（build_records 內 order-based matching）
- Test: `tests/test_generate_data.py`（新建，含 `tests/__init__.py`）

**Interfaces:**
- Produces: `match_manual_row(parsed: dict, manual_rows: List[ManualRow]) -> Optional[ManualRow]` — 行為改變：score fallback 只考慮 `row.source == ""` 的行
- build_records 不再有 order-based matching 分支

- [ ] **Step 1: 寫失敗測試**

建 `tests/__init__.py`（空檔）及 `tests/test_generate_data.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from generate_data import ManualRow, match_manual_row


def make_row(**kw):
    defaults = dict(date="2026/7/15", time="18:00~19:00", court="羽毛球5號場",
                    renter_code="7836", extra_code="8317",
                    renter_name="", extra_name="", source="")
    defaults.update(kw)
    return ManualRow(**defaults)


class MatchManualRowTest(unittest.TestCase):
    def test_exact_source_match_wins(self):
        rows = [make_row(source="a.jpg", court="羽毛球1號場"),
                make_row(source="b.jpg", court="羽毛球2號場")]
        parsed = {"sourceFile": "b.jpg", "date": "", "time": "", "court": "",
                  "renter_code": "", "extra_code": ""}
        self.assertIs(match_manual_row(parsed, rows), rows[1])

    def test_score_fallback_skips_rows_with_source(self):
        # 行有 source 但檔名不同 → 即使欄位全中也不得配對（防錯位）
        rows = [make_row(source="other.jpg")]
        parsed = {"sourceFile": "new.jpg", "date": "2026/7/15",
                  "time": "18:00~19:00", "court": "羽毛球5號場",
                  "renter_code": "7836", "extra_code": "8317"}
        self.assertIsNone(match_manual_row(parsed, rows))

    def test_score_fallback_matches_sourceless_row(self):
        rows = [make_row(source="")]
        parsed = {"sourceFile": "new.jpg", "date": "2026/7/15",
                  "time": "18:00~19:00", "court": "羽毛球5號場",
                  "renter_code": "7836", "extra_code": "8317"}
        self.assertIs(match_manual_row(parsed, rows), rows[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /Users/itlao_cdsj5school/Desktop/運動場地 && python3 -m unittest tests.test_generate_data -v`
Expected: `test_score_fallback_skips_rows_with_source` FAIL（現行 code 會配對成功）；另外兩個 PASS。

- [ ] **Step 3: 改 match_manual_row**

`scripts/generate_data.py` 內，score 迴圈開頭加一行跳過有 source 的行：

```python
    for row in manual_rows:
        if row.source:
            continue  # source-bearing rows only match by exact filename
        score = 0
```

- [ ] **Step 4: 刪除 order-based matching**

`build_records()` 內（約 line 290-303）把：

```python
    records = []
    # Prefer explicit image/source matching. Order-based matching is only safe for
    # older CSV files that do not contain any source filename.
    has_manual_sources = any(row.source for row in manual_rows)
    use_manual_by_order = bool(manual_rows) and not has_manual_sources and len(manual_rows) == len(parsed_images)
    sorted_manual_rows = sorted(manual_rows, key=manual_sort_key)
    sorted_images = sorted(parsed_images, key=record_sort_key)

    for index, parsed in enumerate(sorted_images):
        matched = None
        if use_manual_by_order:
            matched = sorted_manual_rows[index]
        else:
            matched = match_manual_row(parsed, manual_rows)
```

改為：

```python
    records = []
    has_manual_sources = any(row.source for row in manual_rows)

    for parsed in sorted(parsed_images, key=record_sort_key):
        matched = match_manual_row(parsed, manual_rows)
```

同時刪除已無人使用的 `manual_sort_key` 函式（line 221-226）。

- [ ] **Step 5: 跑測試確認通過**

Run: `python3 -m unittest tests.test_generate_data -v`
Expected: 3 個全 PASS。

- [ ] **Step 6: 完整重建驗證無 regression**

Run: `python3 scripts/generate_data.py && python3 -c "import json; d=json.load(open('data/records.json')); print(len(d['records']))"`
Expected: 正常輸出筆數（與改動前相同或更多；不應大幅減少）。

- [ ] **Step 7: Commit**

```bash
git add tests/ scripts/generate_data.py
git commit -m "fix: match manual CSV rows by exact source only; drop order-based fallback

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: daily_ingest.py — 收據解析函式

**Files:**
- Create: `scripts/daily_ingest.py`
- Test: `tests/test_daily_ingest.py`

**Interfaces:**
- Produces:
  - `extract_receipt_id(text: str) -> str` — 回傳 `IDOB…` 正規化編號，找不到回 `""`
  - `looks_like_receipt(text: str) -> bool` — 疑似收據（含關鍵詞）但可能讀不到編號
  - `parse_receipt(text: str) -> dict` — keys: `receipt_id, date, time, court, renter_code, extra_code`（date 格式 `2026/7/15`）
  - `field_count(parsed: dict) -> int` — 非空欄位數（不含 receipt_id）

- [ ] **Step 1: 寫失敗測試**

`tests/test_daily_ingest.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from daily_ingest import extract_receipt_id, looks_like_receipt, parse_receipt, field_count

SAMPLE = """奧林匹克體育中心-羽毛球區
場區編號:羽毛球8號場
收據編號 : IDOB260711073009CKB
使用日期 : 2026-07-14 (=)
使用時段 : 19:00~20:00
租場者 :****1059
額外取場者 :****9963
"""


class ReceiptIdTest(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(extract_receipt_id(SAMPLE), "IDOB260711073009CKB")

    def test_ocr_one_for_i(self):
        self.assertEqual(extract_receipt_id("收據編號: 1DOB260712073009KG1"),
                         "IDOB260712073009KG1")

    def test_space_inside(self):
        self.assertEqual(extract_receipt_id("收據編號 : IDOB26071 2073004WXI"),
                         "IDOB260712073004WXI")

    def test_absent(self):
        self.assertEqual(extract_receipt_id("聯絡人頭像，無收據"), "")


class LooksLikeReceiptTest(unittest.TestCase):
    def test_keyword_hit(self):
        self.assertTrue(looks_like_receipt("...體育局...使用時段..."))

    def test_plain_photo(self):
        self.assertFalse(looks_like_receipt("風景照片"))


class ParseReceiptTest(unittest.TestCase):
    def test_full_parse(self):
        p = parse_receipt(SAMPLE)
        self.assertEqual(p["receipt_id"], "IDOB260711073009CKB")
        self.assertEqual(p["date"], "2026/7/14")
        self.assertEqual(p["time"], "19:00~20:00")
        self.assertEqual(p["court"], "羽毛球8號場")
        self.assertEqual(p["renter_code"], "1059")
        self.assertEqual(p["extra_code"], "9963")
        self.assertEqual(field_count(p), 5)

    def test_partial(self):
        p = parse_receipt("收據編號: IDOB260711073009CKB\n使用時段: 19:00~20:00")
        self.assertEqual(field_count(p), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_daily_ingest -v`
Expected: FAIL — `No module named 'daily_ingest'`

- [ ] **Step 3: 實作解析函式**

`scripts/daily_ingest.py`：

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_daily_ingest -v`
Expected: 全 PASS。（若 `test_space_inside` 失敗，檢查 regex 是否在 compact 後仍容許 12 位下限。）

- [ ] **Step 5: Commit**

```bash
git add scripts/daily_ingest.py tests/test_daily_ingest.py
git commit -m "feat: receipt parsing helpers for daily ingest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: daily_ingest.py — 入庫管線（state、去重、複製、CSV）

**Files:**
- Modify: `scripts/daily_ingest.py`
- Test: `tests/test_daily_ingest.py`（追加）

**Interfaces:**
- Consumes: Task 2 的 `parse_receipt`、`field_count`、`extract_receipt_id`、`looks_like_receipt`
- Produces:
  - `load_state() -> dict` / `save_state(state: dict) -> None` — state 含 `processed_hashes: list[str]`
  - `sha1_of(path: Path) -> str`
  - `list_new_images(state: dict) -> list[Path]` — cache 內 hash 不在 processed 的圖
  - `known_receipt_ids() -> set[str]` — 掃 CSV `source` 欄含 `IDOB` 的檔名抽編號
  - `make_filename(parsed: dict, suffix: str) -> str` — `20260715_IDOBxxx.jpg`
  - `csv_line(parsed: dict, filename: str) -> str` — 一行 CSV（無行尾）
  - `append_csv_lines(lines: list[str]) -> None` — utf-8-sig、CRLF 追加
  - `ingest(dry_run: bool) -> dict` — 回報 `{"added": [...], "incomplete": [...], "suspects": [...]}`；內部呼叫 OCR，複製圖、追加 CSV、更新 state（dry_run 時只報告不落盤）

- [ ] **Step 1: 寫失敗測試（追加到 tests/test_daily_ingest.py）**

```python
import csv
import io
import json
import shutil
import tempfile
import unittest.mock

import daily_ingest
from daily_ingest import (
    make_filename, csv_line, known_receipt_ids, append_csv_lines,
    sha1_of, list_new_images, load_state, save_state, ingest,
)


class FilenameCsvTest(unittest.TestCase):
    def test_make_filename(self):
        parsed = {"receipt_id": "IDOB260712073004WXI", "date": "2026/7/15"}
        self.assertEqual(make_filename(parsed, ".jpg"), "20260715_IDOB260712073004WXI.jpg")

    def test_csv_line(self):
        parsed = {"receipt_id": "IDOBX", "date": "2026/7/15", "time": "20:00~21:00",
                  "court": "羽毛球7號場", "renter_code": "9761", "extra_code": "6175"}
        self.assertEqual(
            csv_line(parsed, "20260715_IDOBX.jpg"),
            "2026/7/15 20:00~21:00,羽毛球7號場,9761,6175,,,20260715_IDOBX.jpg")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "cache").mkdir()
        (self.tmp / "uploads").mkdir()
        (self.tmp / "state").mkdir()
        self.csv_path = self.tmp / "manual.csv"
        header = "使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source\r\n"
        self.csv_path.write_bytes(b"\xef\xbb\xbf" + header.encode("utf-8"))
        self.patches = [
            unittest.mock.patch.object(daily_ingest, "CACHE_DIR", self.tmp / "cache"),
            unittest.mock.patch.object(daily_ingest, "UPLOAD_DIR", self.tmp / "uploads"),
            unittest.mock.patch.object(daily_ingest, "MANUAL_CSV", self.csv_path),
            unittest.mock.patch.object(daily_ingest, "STATE_FILE", self.tmp / "state" / "state.json"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def test_append_csv_keeps_bom_and_crlf(self):
        append_csv_lines(["2026/7/15 20:00~21:00,羽毛球7號場,9761,6175,,,x.jpg"])
        raw = self.csv_path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.endswith(b"x.jpg\r\n"))
        # 不得有裸 LF（全部行尾都是 CRLF）
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_known_receipt_ids_reads_source_column(self):
        append_csv_lines(["2026/7/15 20:00~21:00,,,,,,20260715_IDOBAAA111222333.jpg"])
        self.assertIn("IDOBAAA111222333", known_receipt_ids())

    def test_ingest_dedups_and_copies(self):
        # 兩張同收據圖 + 一張無關圖
        (self.tmp / "cache" / "a.jpg").write_bytes(b"fake-image-1")
        (self.tmp / "cache" / "b.jpg").write_bytes(b"fake-image-2")
        (self.tmp / "cache" / "c.jpg").write_bytes(b"cat-photo")
        ocr_map = {
            "a.jpg": "收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16\n使用時段: 19:00~20:00\n場區編號: 羽毛球3號場\n租場者: ****1234\n額外取場者: ****5678",
            "b.jpg": "收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16",  # 同收據、欄位較少
            "c.jpg": "風景照",
        }
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        side_effect=lambda p: ocr_map[p.name]):
            report = ingest(dry_run=False)
        self.assertEqual(len(report["added"]), 1)
        self.assertTrue((self.tmp / "uploads" / "20260716_IDOB260714073001ABC.jpg").exists())
        content = self.csv_path.read_text(encoding="utf-8-sig")
        self.assertIn("2026/7/16 19:00~20:00,羽毛球3號場,1234,5678,,,20260716_IDOB260714073001ABC.jpg", content)
        # state 記錄了 3 個 hash，重跑不再有新圖
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        side_effect=lambda p: ocr_map[p.name]):
            report2 = ingest(dry_run=False)
        self.assertEqual(report2["added"], [])

    def test_ingest_flags_suspect_without_receipt_id(self):
        (self.tmp / "cache" / "bad.jpg").write_bytes(b"blurry")
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        return_value="體育局 使用時段 糊到讀不到編號"):
            report = ingest(dry_run=False)
        self.assertEqual(report["added"], [])
        self.assertEqual(report["suspects"], ["bad.jpg"])

    def test_ingest_skips_receipt_already_in_csv(self):
        append_csv_lines(["2026/7/16 19:00~20:00,羽毛球3號場,1234,5678,,,20260716_IDOB260714073001ABC.jpg"])
        (self.tmp / "cache" / "dup.jpg").write_bytes(b"same-receipt-again")
        with unittest.mock.patch.object(daily_ingest, "ocr_cache_image",
                                        return_value="收據編號: IDOB260714073001ABC\n使用日期: 2026-07-16\n使用時段: 19:00~20:00"):
            report = ingest(dry_run=False)
        self.assertEqual(report["added"], [])
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m unittest tests.test_daily_ingest -v`
Expected: ImportError（make_filename 等不存在）。

- [ ] **Step 3: 實作管線**

追加到 `scripts/daily_ingest.py`：

```python
import csv
import hashlib
import io
import json
import shutil

from generate_data import available_tesseract_languages, ocr_image  # noqa: E402

CSV_HEADER = "使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source"

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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m unittest tests.test_daily_ingest -v`
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add scripts/daily_ingest.py tests/test_daily_ingest.py
git commit -m "feat: ingest pipeline with receipt dedup and CSV append

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: daily_ingest.py — git 同步、通知、main()

**Files:**
- Modify: `scripts/daily_ingest.py`
- Test: 手動 dry-run（git/osascript 為薄包裝，不做單元測試）

**Interfaces:**
- Consumes: Task 3 的 `ingest`
- Produces:
  - `git_sync(added: list[str]) -> None` — `pull --rebase` → `add`（新圖+CSV）→ `commit` → `push`；無新增時不動
  - `notify(title: str, message: str) -> None` — osascript display notification
  - `main() -> int` — argparse：`--dry-run`（只報告）、`--bootstrap`（把現有 cache 全標已處理，不入庫）；log 同時寫檔案與 stdout

- [ ] **Step 1: 實作**

追加到 `scripts/daily_ingest.py`：

```python
import argparse
import logging
import subprocess
from datetime import datetime


def notify(title: str, message: str) -> None:
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def git_sync(added: list) -> None:
    def run(*args):
        subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True)

    run("pull", "--rebase", "origin", "main")
    for filename in added:
        run("add", str(UPLOAD_DIR / filename))
    run("add", str(MANUAL_CSV))
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

    if report["added"]:
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
```

- [ ] **Step 2: 全部測試重跑**

Run: `python3 -m unittest discover tests -v`
Expected: 全 PASS（新 import 不破壞舊測試）。

- [ ] **Step 3: 真機 dry-run**

Run: `python3 scripts/daily_ingest.py --bootstrap && python3 scripts/daily_ingest.py --dry-run`
Expected: bootstrap 標記 33 張左右；dry-run 回報 `added: []`（cache 已全部標記）。確認 `~/Library/Logs/badminton-ingest.log` 有內容。

- [ ] **Step 4: Commit**

```bash
git add scripts/daily_ingest.py
git commit -m "feat: git sync, macOS notification and CLI for daily ingest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: launchd 排程

**Files:**
- Create: `scripts/com.badminton.daily-ingest.plist`（repo 內留範本）
- Install: `~/Library/LaunchAgents/com.badminton.daily-ingest.plist`

**Interfaces:**
- Consumes: Task 4 的 `main()`（`daily_ingest.py` 無參數執行 = 正式入庫）

- [ ] **Step 1: 確認 python3 絕對路徑**

Run: `which python3 && which tesseract`
Expected: 類似 `/opt/homebrew/bin/python3`、`/opt/homebrew/bin/tesseract`。plist 用查到的 python3 路徑。

- [ ] **Step 2: 寫 plist**

`scripts/com.badminton.daily-ingest.plist`（`/opt/homebrew/bin/python3` 按 Step 1 結果調整）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.badminton.daily-ingest</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/python3</string>
        <string>/Users/itlao_cdsj5school/Desktop/運動場地/scripts/daily_ingest.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>10</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/itlao_cdsj5school/Library/Logs/badminton-ingest.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/itlao_cdsj5school/Library/Logs/badminton-ingest.log</string>
</dict>
</plist>
```

- [ ] **Step 3: 安裝並載入**

```bash
cp scripts/com.badminton.daily-ingest.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.badminton.daily-ingest.plist
launchctl list | grep badminton
```

Expected: `launchctl list` 顯示 `com.badminton.daily-ingest`。

- [ ] **Step 4: 手動觸發一次驗證**

```bash
launchctl kickstart gui/$(id -u)/com.badminton.daily-ingest
sleep 5 && tail -5 ~/Library/Logs/badminton-ingest.log
```

Expected: log 有本次執行紀錄（bootstrap 已做過，應為 `added=[]` 或正常新增）。

- [ ] **Step 5: Commit**

```bash
git add scripts/com.badminton.daily-ingest.plist
git commit -m "feat: launchd schedule for daily ingest at 10:30

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push origin main
```
