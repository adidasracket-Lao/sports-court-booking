# 每日自動更新場地紀錄（daily auto-ingest）設計

日期：2026-07-13
狀態：已獲用戶批准

## 背景與問題

現時流程：Telegram 傳圖 → Hermes 存到 `~/.hermes/image_cache/` → 人手搬圖到 repo、人手寫 CSV、人手 push → CI 每日 11:00（澳門時間）重建網站。

三個「人手」步驟造成：
1. 忘記 push，11:00 的 CI build 白跑，網站沒更新
2. CSV 對位錯誤：`generate_data.py` 在 CSV 行數等於圖片數時按排序硬配，同時段多場易錯位，導致網站同一行「圖片內容跟左邊文字對不上」
3. 同一收據拍多次造成重複

## 目標

用戶日常只做一件事：在 Telegram 傳圖給 Hermes。其餘全自動。

## 設計

### 新增 `scripts/daily_ingest.py`（本機執行）

1. 掃 `~/.hermes/image_cache/`，用檔案內容 hash 與 `uploads/` 已有圖片比對，找出新圖
2. 每張新圖跑 `tesseract`（`chi_tra+eng`）：
   - 讀不到收據編號（regex `IDOB[A-Z0-9]+`）→ 跳過（視為非場地收據）
   - 讀到 → 抽取：收據編號、使用日期、使用時段、場地編號、租場者後四碼、額外取場者後四碼
3. 收據編號為唯一 key：
   - 同一收據多張圖只取一張（取 OCR 欄位最齊那張）
   - 收據編號已存在於 CSV（source 檔名含該編號）→ 跳過
4. 新圖改名為 `{YYYYMMDD}_{收據編號}.jpg` 複製到 `uploads/`
5. 在 `場地租用資料.csv` 追加一行；OCR 讀不到的欄位留空；`source` 填新檔名
   - CSV 為 UTF-8 with BOM、CRLF 行尾（與現有檔一致）
6. 有新增才 `git add`（只加新圖與 CSV）、`commit`、`push origin main`
7. 結尾用 `osascript` 發 macOS 通知：
   - 成功：「新增 N 筆，M 筆欄位不全需人手補」
   - 有疑似收據但讀不到編號的圖 → 通知列出，人手檢查
   - 任何步驟失敗（OCR、git push）→ 通知失敗原因
8. log 寫 `~/Library/Logs/badminton-ingest.log`

### 修改 `scripts/generate_data.py`

- 手動 CSV 與圖片對位：只按 `source` 欄位對檔名，**刪除「行數相等時按排序硬配」的 fallback**
- 保留 score 匹配作為無 source 時的後備（舊資料相容）

### launchd 排程

- `~/Library/LaunchAgents/com.badminton.daily-ingest.plist`
- `StartCalendarInterval` 每日 10:30（澳門本地時間）；Mac 睡眠錯過，喚醒後 launchd 自動補跑
- 執行 `daily_ingest.py`，stdout/stderr 導向 log

### 不改動的部分

- CI（`deploy-pages.yml`）維持 11:00 cron 重建
- 5 小時寬限期的過期隱藏/刪圖邏輯不變
- `取場人對照表.csv` 姓名對照不變

## 風險與對策

| 風險 | 對策 |
|------|------|
| 真收據 OCR 太差，連 IDOB 編號都讀不到而被漏掉 | 「含『收據/體育局/羽毛球』字樣但無編號」的圖列入通知，人手檢查 |
| 10:30 Mac 關機/睡眠 | launchd 喚醒補跑；當日錯過則次日補上（收據編號去重保證不會重複） |
| image_cache 含非場地圖片 | 必須讀到 IDOB 編號才入庫 |
| git push 衝突（用戶手動 push 過） | 腳本先 `git pull --rebase` 再 push；失敗發通知 |

## 驗收標準

1. 在 Telegram 傳一批場地圖後，翌日 10:30 腳本自動入庫並 push，11:00 網站更新
2. 同一收據傳兩次只產生一筆紀錄
3. 網站每行圖片與文字欄位一致（source 精確對位）
4. OCR 缺欄的紀錄欄位留空顯示，且有 macOS 通知提示
