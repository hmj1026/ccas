# fubon-fetcher-impl Specification

## Purpose
TBD - created by archiving change add-fubon-bank-support. Update Purpose after archive.
## Requirements
### Requirement: FubonFetcher 實作 BankFetcher 介面

系統 SHALL 提供 `FubonFetcher` 類別，繼承 `BankFetcher`，設定 `bank_code = "FUBON"`。

#### Scenario: fetcher 宣告正確的 bank_code
- **WHEN** 檢查 `FubonFetcher` 的屬性
- **THEN** `bank_code` SHALL 為 `"FUBON"`

### Requirement: can_fetch 辨識富邦下載連結

`FubonFetcher.can_fetch()` SHALL 從郵件 HTML body 中偵測任何指向 FUBON 官方帳單下載網域（`_ALLOWED_DOMAINS`）的 `<a>` 錨點，以支援富邦帳單系統遷移為 SPA 後以圖片按鈕取代純文字連結的郵件格式。辨識邏輯不再依賴錨點內的文字內容。

#### Scenario: 錨點內為 img 按鈕（SPA 時代新格式）
- **WHEN** HTML body 包含 `<a href="https://fbmbill.taipeifubon.com.tw/..."><img alt="下載本期帳單(PDF)" /></a>`
- **THEN** `can_fetch()` SHALL 回傳 `True`

#### Scenario: 錨點內為純文字（舊格式，保留相容）
- **WHEN** HTML body 包含 `<a href="https://mybank.taipeifubon.com.tw/...">下載帳單明細</a>`
- **THEN** `can_fetch()` SHALL 回傳 `True`

#### Scenario: 錨點指向非 FUBON 官方網域
- **WHEN** HTML body 包含的所有 `<a href="...">` 均指向 `_ALLOWED_DOMAINS` 以外的網域
- **THEN** `can_fetch()` SHALL 回傳 `False`

#### Scenario: 空或無效 HTML 不導致例外
- **WHEN** HTML body 為 None、空字串或無效 HTML
- **THEN** `can_fetch()` SHALL 回傳 `False`，不拋出例外

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 嘗試從郵件 HTML 下載 PDF 帳單。當目標下載系統（`fbmbill.taipeifubon.com.tw` 等）為 SPA + API + 可能 OTP 的架構且自動化流程尚未實作時，SHALL fallback 至 **manual staging 目錄** 搜尋由使用者手動放入的 PDF 檔案。僅當 HTML 路徑與 manual staging 路徑**兩者皆無可用檔案**時，SHALL 拋出 `FetchError`，錯誤訊息 MUST 明確指引使用者將 PDF 放入 manual staging 目錄。

SPA 自動下載路徑：從郵件 HTML 抽出 serialKey、開啟 SPA session、取得並辨識圖形驗證碼、POST `doLogin` 取得 JWT、最後下載本期 PDF bytes。Captcha 辨識 SHALL 走 **captcha-specialized OCR（ddddocr）** 主路徑，受 `conf ≥ 0.80`、`len == 4`、`全為 0-9 數字` 三重 gate 控制；`conf` 來源 SHALL 為 ddddocr `classification(jpeg, probability=True)` 回傳 dict 的 `confidence` 欄位（library 端聚合後的 CTC-aware aggregate）。被 gate 拒絕時 SHALL 重抽 captcha 並重試，最多 `FUBON_CAPTCHA_MAX_RETRIES` 次（預設 7，本 change 不改）。當 `FUBON_CAPTCHA_FALLBACK_LLM=1` 時，OCR 被 gate 拒絕後 SHALL 嘗試呼叫 LLM fallback；無論 fallback 是否成功，都算一次 retry。Retry 全部耗盡後 SHALL 拋出 `FetchError(bank_code="FUBON", reason="captcha_retry_exhausted")`，讓 pipeline 降級到 manual staging。當 `FUBON_ID_NUMBER` 或 `FUBON_BIRTHDAY` 未設定時，`fetch_pdf()` SHALL 在進入網路 flow 前就拋出 `FetchError(bank_code="FUBON", reason="credentials_missing")`。

`captcha.solve(jpeg_bytes) -> CaptchaResult | None` 的外部介面、回傳語意與 gate 行為 SHALL 與既有契約完全一致：`solve()` 成功時回傳 `CaptchaResult(text: str, confidence: float)`（`text` 為 4 位數字），任何 gate 不通過或底層推論失敗時 SHALL 回傳 `None`；flow 層 SHALL NOT 因 solver 實作替換而變動。模組底層 SHALL NOT 依賴 `easyocr`、`torch`、`torchvision`。

#### Scenario: 完整 happy path（credentials 齊全、captcha 一次過）

- **WHEN** `FUBON_ID_NUMBER` 與 `FUBON_BIRTHDAY` 均已設定，且 ddddocr 第一次辨識結果 `confidence ≥ 0.80 && len == 4 && isdigit()`，且 `doLogin` 回 `code: 0`
- **THEN** `fetch_pdf()` SHALL 完成 Step 1~6 並回傳 PDF bytes（以 `b"%PDF"` 開頭）

#### Scenario: credentials 未設定

- **WHEN** `Settings.fubon_id_number` 為 `None`
- **THEN** `fetch_pdf()` SHALL 拋出 `FetchError(bank_code="FUBON", reason="credentials_missing")`，且 SHALL NOT 發出任何 HTTP request

#### Scenario: Captcha 前 N 次被 gate 拒、第 N+1 次通過

- **WHEN** `FUBON_CAPTCHA_MAX_RETRIES=7`，前 3 次 ddddocr 回 `None`（被 gate 拒，例：`confidence < 0.80` 或 `len != 4`），第 4 次通過三重 gate
- **THEN** `fetch_pdf()` SHALL 呼叫 `checkImgs/captcha.jpg` 共 4 次、`doLogin` 共 1 次，並成功回傳 PDF bytes

#### Scenario: Captcha retry 全部耗盡

- **WHEN** `FUBON_CAPTCHA_MAX_RETRIES=7`，7 次 ddddocr 全部被 gate 拒絕且 `FUBON_CAPTCHA_FALLBACK_LLM=0`
- **THEN** `fetch_pdf()` SHALL 拋出 `FetchError(bank_code="FUBON", reason="captcha_retry_exhausted")`

#### Scenario: doLogin 回報 id 錯誤不 retry

- **WHEN** ddddocr 辨識成功但 `doLogin` 回應錯誤代碼被分類為 `id_wrong`
- **THEN** `fetch_pdf()` SHALL 立即拋出 `FetchError(bank_code="FUBON", reason="credentials_wrong")`，不再重抽 captcha

#### Scenario: LLM fallback 啟用且 OCR 失敗時被呼叫

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=1`，ddddocr 回 `None`
- **THEN** `fetch_pdf()` SHALL 呼叫 `captcha_llm.solve_with_llm(jpeg)`，成功則用回傳值作為 `captcha_answer` 嘗試 `doLogin`

#### Scenario: LLM fallback 未啟用時 anthropic 不被 import

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=0` 且執行完整 `fetch_pdf` flow
- **THEN** `sys.modules` SHALL NOT 包含 `anthropic` 模組

#### Scenario: 主 solver 在 fixture regression 達到 accept rate ≥ 80%

- **WHEN** 對 `tests/fixtures/fubon/captcha_samples/` 內所有標註樣本（檔名為 ground truth，數量 SHALL ≥ 10）逐一呼叫 `captcha.solve()`
- **THEN** `accepted / total` SHALL ≥ 0.80，且所有 `accepted` 的 `CaptchaResult.text` SHALL 等於對應檔名的 ground truth（false positive rate = 0）

#### Scenario: solver 底層不依賴 easyocr / torch

- **WHEN** 在已安裝 ccas backend 的環境執行 `python -c "import ccas.ingestor.fetcher.banks.fubon.captcha; import sys; assert 'easyocr' not in sys.modules and 'torch' not in sys.modules"`
- **THEN** 指令 SHALL 成功退出（exit 0），且 `pyproject.toml` 主依賴 SHALL NOT 包含 `easyocr`、`torch`、`torchvision`

#### Scenario: SPA 路徑失敗時 fallback 至 manual staging（檔案存在）

- **GIVEN** `fetch_pdf()` 被呼叫且 HTML 解析路徑因 SPA 網域失敗
- **AND** `Settings.fubon_manual_staging_dir` 目錄內存在對應月份的 `.pdf` 檔案
- **WHEN** fetcher 執行 fallback
- **THEN** SHALL 從 manual staging move 該 PDF 至 `Settings.staging_dir/FUBON/`，回傳該路徑，不拋例外

#### Scenario: Manual staging 目錄為空時拋出明確 FetchError

- **GIVEN** HTML 路徑失敗且 manual staging 目錄為空
- **WHEN** `fetch_pdf()` 被呼叫
- **THEN** SHALL 拋出 `FetchError`，`bank_code="FUBON"`，訊息 MUST 包含 manual staging 目錄絕對路徑與建議動作「從富邦網銀下載 PDF 並放入該目錄」

#### Scenario: 檔名含帳單月份時精確配對

- **GIVEN** manual staging 目錄含 `fubon-2026-03.pdf` 與 `fubon-2026-04.pdf`
- **AND** 觸發 fetch 的 Gmail message 推導出帳單月份為 `2026-03`
- **WHEN** fetcher 選檔
- **THEN** SHALL 選到 `fubon-2026-03.pdf`

#### Scenario: 檔名不含月份時採 mtime 最新

- **GIVEN** manual staging 目錄內只有 `statement.pdf` 單一檔案且檔名不含月份
- **WHEN** fetcher 選檔
- **THEN** SHALL 選到該檔案

#### Scenario: 多檔無法區分月份時拋 FetchError

- **GIVEN** manual staging 內有 2 個無月份檔名且 mtime 相近
- **WHEN** fetcher 選檔
- **THEN** SHALL 拋出 `FetchError`，訊息包含「manual staging 目錄有多個無法對應的檔案」

#### Scenario: URL 提取失敗（HTML 無下載連結）仍走 fallback

- **GIVEN** HTML body 中找不到任何指向 `_ALLOWED_DOMAINS` 的連結
- **AND** manual staging 目錄有可用檔案
- **WHEN** `fetch_pdf()` 被呼叫
- **THEN** SHALL 進入 manual staging 路徑並成功回傳，不拋 `FetchError`

### Requirement: FubonFetcher 自動註冊至 FetcherRegistry

`fubon` 模組載入時 SHALL 自動將 `FubonFetcher` 實例註冊至 `FetcherRegistry`。

#### Scenario: import 後 registry 包含 FUBON fetcher
- **WHEN** `ccas.ingestor.fetcher.banks.fubon` 模組被 import
- **THEN** `fetcher_registry.get("FUBON")` SHALL 回傳 `FubonFetcher` 實例

