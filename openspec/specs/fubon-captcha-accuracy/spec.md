## ADDED Requirements

### Requirement: Captcha 圖片前處理提升 OCR 辨識率

系統 SHALL 在呼叫 ddddocr 前對 captcha JPEG 執行前處理 pipeline：灰階轉換 → 對比增強 → 二值化（Otsu threshold）→ 降噪（median filter）。前處理 SHALL 封裝為純函式 `_preprocess(jpeg_bytes: bytes) -> bytes`。

#### Scenario: 前處理後 OCR 準確率提升
- **WHEN** 以 ≥30 張真實 captcha fixture 執行 OCR
- **THEN** 前處理後的 ground truth accuracy SHALL ≥ 80%

#### Scenario: 前處理不影響 gate 邏輯
- **WHEN** 前處理後的圖片送入 ddddocr
- **THEN** 既有 gate 條件（4 碼純數字、confidence ≥ 0.80）SHALL 維持不變

#### Scenario: 前處理容錯
- **WHEN** 輸入的 JPEG 為損壞或非標準格式
- **THEN** `_preprocess()` SHALL 回傳原始 bytes 不拋出例外

### Requirement: Captcha eval harness

系統 SHALL 提供 `scripts/eval_captcha.py`，以 fixture 目錄為輸入，統計 accept rate 與 ground truth accuracy。

#### Scenario: 執行 eval 並輸出統計
- **WHEN** 執行 `uv run python scripts/eval_captcha.py --fixtures-dir tests/fixtures/fubon/captcha_samples/`
- **THEN** SHALL 輸出 `total`, `accepted`, `correct`, `accept_rate`, `accuracy` 欄位，exit code 0

#### Scenario: Accuracy 低於門檻時警告
- **WHEN** ground truth accuracy < 80%
- **THEN** eval script SHALL 以 exit code 1 結束並輸出警告訊息

### Requirement: Fixture 集擴充至 ≥30 張

`tests/fixtures/fubon/captcha_samples/` SHALL 包含至少 30 張真實富邦 captcha JPEG，檔名為 ground truth 答案（如 `2080.jpg`）。

#### Scenario: Fixture 數量充足
- **WHEN** 檢查 fixture 目錄
- **THEN** 目錄 SHALL 包含 ≥ 30 個 `.jpg` 檔案

### Requirement: Pipeline 執行時自動收集 captcha 樣本

系統 SHALL 在 `flow.download()` 成功取得 captcha + server 回傳正確/錯誤結果後，將 captcha JPEG 儲存至 `data/captcha-archive/` 目錄，檔名包含 ground truth（若 server 接受）或 `unknown`（若 server 拒絕）。此功能 SHALL 預設關閉，透過 `FUBON_CAPTCHA_ARCHIVE=true` 環境變數啟用。

#### Scenario: 啟用時自動儲存
- **WHEN** `FUBON_CAPTCHA_ARCHIVE=true` 且 captcha 通過 server 驗證
- **THEN** JPEG SHALL 儲存至 `data/captcha-archive/<answer>.jpg`

#### Scenario: 預設不啟用
- **WHEN** `FUBON_CAPTCHA_ARCHIVE` 未設定或為 false
- **THEN** 不 SHALL 儲存任何 captcha 檔案
