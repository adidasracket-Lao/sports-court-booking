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

Latest verified record wins. Never delete historical source images.

## CSV Schema

Current CSV schema:

```csv
使用時間,場地編號,租場者,額外取場者,租場者(姓名）,額外取場者（姓名）,source
```

Example:

```csv
2026/4/30 17:00~18:00,羽毛球5號場,9709,4198,,俊溢,IMG_4145.jpg
```

`source` is important: it pins a manual verified row to the exact image file, avoiding wrong order-based matching.

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
python3 scripts/generate_data.py
git add .
git commit -m "daily sports update"
git push
```

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

## Safety

- Never delete historical records or uploaded images.
- Only merge or correct records.
- Keep source screenshots in `uploads/`.
- Keep verified CSV rows with `source` filename.


## Telegram 自動處理設定

當使用者透過 Telegram 上傳澳門體育局 booking.sport.gov.mo 的二維碼 / 收據截圖，並要求更新運動場地網站時，預設自動處理整批圖片：

1. 偵測所有新上傳的相關圖片，不只處理第一張。
2. 全部存入 `uploads/`，使用下一個 `IMG_####.jpg` 檔名。
3. 讀取日期、時段、場區編號、租場者後四碼、額外取場者後四碼及姓名。
4. 更新 `場地租用資料.csv`，並以 `source` 對應圖片。
5. 執行 `python3 scripts/generate_data.py` 更新 `data/records.json`。
6. 網站前台隱藏過期場地；原始 CSV / JSON / 圖片保留。
7. commit、push、等待 GitHub Pages 部署完成，驗證後回傳網址。

只有在圖片讀不到、資料矛盾、重複判斷不清或部署失敗時，才需要先問使用者。
