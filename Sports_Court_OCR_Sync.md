# Sports Court OCR Sync

## Goal
Automatically read Macau Sports Bureau booking JPG/PNG tickets, extract booking information, merge into CSV, generate website JSON, and publish the updated GitHub Pages site.

Target website:
https://adidasracket-lao.github.io/sports-court-booking/

Run schedule:
Every day 11:00 AM Macau Time

## Current Project Structure

```text
運動場地/
  uploads/                 # source ticket screenshots
  data/records.json         # website data source
  場地租用資料.csv           # manual/verified booking rows
  取場人對照表.csv           # member mapping
  scripts/generate_data.py  # OCR + merge + JSON builder
  scripts/prune_expired_uploads.py  # delete expired source screenshots to reduce OCR/token waste
  index.html
  app.js
  styles.css
```

## OCR Extraction Rules

Input: jpg/png screenshots in `uploads/`

Extract fields:

| Chinese label | field |
|---|---|
| 使用日期 | date |
| 使用時段 | time |
| 場區編號 | court |
| 租場者 | renter_id |
| 額外取場者 | extra_id |

### Image-first data rule

The image is the source of truth for booking facts. When the website table
shows text fields on the left and the original image on the right, the text
must match the information visible in the image.

Use OCR/image text first for these fields whenever the value is confidently
readable:

```text
日期
時間
球場編號
取場人
額外取場人
取場人姓名
額外取場人姓名
```

If OCR cannot confidently read a field, use the row pinned by the image filename
(`source` / `圖片`) as the fallback. Never let an order-based match override a
field that is clearly readable from the image.

For renter codes, accept only confident masked-code patterns such as:

```text
****1234
####1234
```

Do not treat general 3-4 digit numbers as renter codes. In particular, never use
dates or years such as `2026` as `取場人` or `額外取場人`.

## Normalize

Date:

```text
2026-04-30 → 2026/4/30
```

Time:

```text
17:00-18:00
17:00~18:00
17:00～18:00
→ 17:00~18:00
```

Court:

```text
羽毛球場A / 羽毛球A / A / Court A → 羽毛球場A
羽毛球5號場 / 5號 / 5號場 → 羽毛球5號場
```

## Member Mapping

Use `取場人對照表.csv`.

Known mappings:

```text
843 → Wing
6175 → 嘉浩
7481 → 庭彰
6492 → 譚健朗
9761 → 康
1103 → 戴
6185 → 杜
4932 → Matthew
8317 → 卓謙
1086 → 柏熙
4198 → 俊溢
```

If not found: name = empty string.

## Duplicate Rule

Unique key:

```text
date + time + court
```

Do not include renter code or extra renter code in the display duplicate key.
If multiple records resolve to the same `date + time + court`, show only one on
the website. This prevents repeated display of the same booking/image
information even when renter-code OCR or manual rows differ.

Latest verified record wins. Never delete historical source images.

The image filename must still remain unique: one displayed row should point to
one source image, and the same image file must not be displayed multiple times.

## CSV Schema

Supported CSV schemas:

```csv
使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source
```

```csv
日期,時間,球場編號,取場人,額外取場人,取場人姓名,額外取場人姓名,圖片
```

Example:

```csv
2026/4/30 17:00~18:00,羽毛球5號場,9709,4198,,俊溢,IMG_4145.jpg
```

`source` / `圖片` is important: it pins a verified row to the exact image file,
avoiding wrong order-based matching. When a mismatch is found, correct the CSV
row so the left-side text matches the right-side image.

### Mismatch correction rule

When a row's text data and the source image disagree:

1. Trust the source image.
2. Correct the CSV row directly to match the image.
3. Regenerate `data/records.json`.
4. Verify there are no duplicate `sourceFile` values and no duplicate
   `date + time + court` display keys.

## Website JSON

Generated file:

```text
data/records.json
```

Website reads this file directly.

## Execution

Manual run:

```sh
cd ~/Desktop/運動場地
python3 scripts/prune_expired_uploads.py --apply
python3 scripts/generate_data.py
git add .
git commit -m "daily sports update"
git push
```

`prune_expired_uploads.py` deletes only screenshots whose booking end time is already past. Verified rows remain in `場地租用資料.csv`; `generate_data.py` preserves those historical records even when the image file has been removed.

GitHub Actions will deploy GitHub Pages after push.

## Verification

After push, verify:

```text
https://adidasracket-lao.github.io/sports-court-booking/
```

Concise report format:

```text
新增:
更新:
重複:
失敗:
Done.
```

Data integrity checks:

```sh
python3 scripts/generate_data.py
python3 - <<'PY'
import collections, json
records = json.load(open("data/records.json", encoding="utf-8"))["records"]
sources = collections.Counter(r.get("sourceFile") for r in records if r.get("sourceFile"))
keys = collections.Counter((r.get("date"), r.get("time"), r.get("court")) for r in records)
print("duplicate sources:", [item for item in sources.items() if item[1] > 1])
print("duplicate date/time/court:", [item for item in keys.items() if item[1] > 1])
PY
```

Both duplicate lists should be empty before upload/publish.

## Safety

- Keep verified CSV rows with `source` filename.
- Historical records may remain in CSV/JSON after their screenshots are deleted.
- It is OK to delete expired source screenshots from `uploads/` after their booking end time has passed, to reduce future OCR/token waste.
- Never delete future/active booking screenshots unless the user explicitly asks.
- Only merge or correct records.


## Telegram 自動處理設定

### 每日 11:00 批次更新規則

使用者平常會透過 Telegram 上傳「運動場地」圖片。為降低錯位、重複、漏圖和 OCR 誤讀風險，Hermes / 自動代理不要每收到一張圖片就立即更新網站；應先收集當日上傳的整批圖片，並在每天澳門時間 11:00 統一核對、生成、上傳和部署。

11:00 批次處理時必須執行完整核對：

1. 確認 Telegram 上傳的所有運動場地圖片都已存入 `uploads/`。
2. 以圖片資訊為主更新 `場地租用資料.csv`。
3. 執行 `python3 scripts/generate_data.py` 更新 `data/records.json`。
4. 檢查不可有重複 `sourceFile`。
5. 檢查不可有重複 `日期 + 時間 + 球場` 顯示資料。
6. 檢查左邊文字資料必須和右邊圖片一致。
7. 檢查不可把日期年份，例如 `2026`，誤當作取場人或額外取場人。
8. 只有在核對通過後，才 commit、push、等待 GitHub Pages 部署完成。

如果圖片模糊、截圖不完整、資料矛盾、重複判斷不清、OCR 讀不到關鍵欄位或部署失敗，先問使用者，不要直接發布可疑資料。

當使用者透過 Telegram 上傳澳門體育局 booking.sport.gov.mo 的二維碼 / 收據截圖，並要求更新運動場地網站時，預設自動處理整批圖片：

1. 偵測所有新上傳的相關圖片，不只處理第一張。
2. 全部存入 `uploads/`，使用下一個 `IMG_####.jpg` 檔名。
3. 讀取日期、時段、場區編號、租場者後四碼、額外取場者後四碼及姓名；圖片 OCR 有可信資料時必須優先使用。
4. 更新 `場地租用資料.csv`，並以 `source` / `圖片` 對應圖片；左邊文字資料必須和右邊圖片一致。
5. 先執行 `python3 scripts/prune_expired_uploads.py --apply`，刪除已過期的 `uploads/` 圖片，避免之後重複 OCR 浪費 token。
6. 執行 `python3 scripts/generate_data.py` 更新 `data/records.json`。
7. 檢查不可有重複 `sourceFile`，也不可有重複 `日期 + 時間 + 球場` 顯示資料。
8. 網站前台隱藏過期場地；原始 CSV / JSON 保留，過期圖片可刪除。
9. commit、push、等待 GitHub Pages 部署完成，驗證後回傳網址。

只有在圖片讀不到、資料矛盾、重複判斷不清或部署失敗時，才需要先問使用者。
