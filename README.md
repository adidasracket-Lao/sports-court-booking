# 運動場地租用網站

這個專案可直接部署到 GitHub Pages，功能包含：

- 讀取 `uploads/` 內的圖片
- 以 OCR 抽取日期、時間、球場、取場人、額外取場人
- 依 `取場人對照表.csv` 補上姓名
- 在網站表格提供原圖下載
- 透過 GitHub Actions 每天澳門時間上午 11:00 自動重建網站

## 檔案結構

- `index.html`：網站頁面
- `app.js`：前端表格與本機預覽上傳
- `styles.css`：網站樣式
- `scripts/generate_data.py`：OCR 與資料整理腳本
- `uploads/`：放置要辨識的圖片
- `取場人對照表.csv`：後四碼對照姓名

## 使用方式

1. 把新圖片放進 `uploads/`
2. 更新 `取場人對照表.csv` 或 `場地租用資料.csv`（如需要）
3. 推到 GitHub `main` branch
4. 到 GitHub repository 的 `Settings > Pages`
5. 選擇 `GitHub Actions` 作為來源

之後每次 push 都會更新網站，排程也會在每天 `03:00 UTC` 自動重建一次，對應澳門時間 `11:00`。
