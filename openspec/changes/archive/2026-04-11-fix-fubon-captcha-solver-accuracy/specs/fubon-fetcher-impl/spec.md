# Delta: fubon-fetcher-impl (fix-fubon-captcha-solver-accuracy)

## MODIFIED Requirements

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 執行完整的 SPA 下載 pipeline：從郵件 HTML 抽出 serialKey、開啟 SPA session、取得並辨識圖形驗證碼、POST `doLogin` 取得 JWT、最後下載本期 PDF bytes。Captcha 辨識 SHALL 走 **captcha-specialized OCR（ddddocr）** 主路徑，受 `conf ≥ 0.80`、`len == 4`、`全為 0-9 數字` 三重 gate 控制；`conf` 來源 SHALL 為 ddddocr `classification(jpeg, probability=True)` 回傳 dict 的 `confidence` 欄位（library 端聚合後的 CTC-aware aggregate）。被 gate 拒絕時 SHALL 重抽 captcha 並重試，最多 `FUBON_CAPTCHA_MAX_RETRIES` 次（預設 7，本 change 不改）。當 `FUBON_CAPTCHA_FALLBACK_LLM=1` 時，OCR 被 gate 拒絕後 SHALL 嘗試呼叫 LLM fallback；無論 fallback 是否成功，都算一次 retry。Retry 全部耗盡後 SHALL 拋出 `FetchError(bank_code="FUBON", reason="captcha_retry_exhausted")`，讓 pipeline 降級到 manual staging。當 `FUBON_ID_NUMBER` 或 `FUBON_BIRTHDAY` 未設定時，`fetch_pdf()` SHALL 在進入網路 flow 前就拋出 `FetchError(bank_code="FUBON", reason="credentials_missing")`。

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
