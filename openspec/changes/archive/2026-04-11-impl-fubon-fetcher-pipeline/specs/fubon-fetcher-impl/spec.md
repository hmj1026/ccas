## MODIFIED Requirements

### Requirement: fetch_pdf 完成完整下載流程

`FubonFetcher.fetch_pdf()` SHALL 執行完整的 SPA 下載 pipeline：從郵件 HTML 抽出 serialKey、開啟 SPA session、取得並辨識圖形驗證碼、POST `doLogin` 取得 JWT、最後下載本期 PDF bytes。Captcha 辨識 SHALL 走 EasyOCR 主路徑，受 `conf ≥ 0.80` 與 `len == 4` 雙重 gate 控制；被 gate 拒絕時 SHALL 重抽 captcha 並重試，最多 `FUBON_CAPTCHA_MAX_RETRIES` 次（預設 7）。當 `FUBON_CAPTCHA_FALLBACK_LLM=1` 時，OCR 被 gate 拒絕後 SHALL 嘗試呼叫 LLM fallback；無論 fallback 是否成功，都算一次 retry。Retry 全部耗盡後 SHALL 拋出 `FetchError(bank_code="FUBON", reason="captcha_retry_exhausted")`，讓 pipeline 降級到 manual staging。當 `FUBON_ID_NUMBER` 或 `FUBON_BIRTHDAY` 未設定時，`fetch_pdf()` SHALL 在進入網路 flow 前就拋出 `FetchError(bank_code="FUBON", reason="credentials_missing")`。

#### Scenario: 完整 happy path（credentials 齊全、captcha 一次過）

- **WHEN** `FUBON_ID_NUMBER` 與 `FUBON_BIRTHDAY` 均已設定，且 EasyOCR 第一次辨識結果 `conf ≥ 0.80 && len == 4`，且 `doLogin` 回 `code: 0`
- **THEN** `fetch_pdf()` SHALL 完成 Step 1~6 並回傳 PDF bytes（以 `b"%PDF"` 開頭）

#### Scenario: credentials 未設定

- **WHEN** `Settings.fubon_id_number` 為 `None`
- **THEN** `fetch_pdf()` SHALL 拋出 `FetchError(bank_code="FUBON", reason="credentials_missing")`，且 SHALL NOT 發出任何 HTTP request

#### Scenario: Captcha 前 N 次被 gate 拒、第 N+1 次通過

- **WHEN** `FUBON_CAPTCHA_MAX_RETRIES=7`，前 3 次 OCR 回 `None`（被 gate 拒），第 4 次成功
- **THEN** `fetch_pdf()` SHALL 呼叫 `checkImgs/captcha.jpg` 共 4 次、`doLogin` 共 1 次，並成功回傳 PDF bytes

#### Scenario: Captcha retry 全部耗盡

- **WHEN** `FUBON_CAPTCHA_MAX_RETRIES=7`，7 次 OCR 全部被 gate 拒絕且 `FUBON_CAPTCHA_FALLBACK_LLM=0`
- **THEN** `fetch_pdf()` SHALL 拋出 `FetchError(bank_code="FUBON", reason="captcha_retry_exhausted")`

#### Scenario: doLogin 回報 id 錯誤不 retry

- **WHEN** OCR 辨識成功但 `doLogin` 回應錯誤代碼被分類為 `id_wrong`
- **THEN** `fetch_pdf()` SHALL 立即拋出 `FetchError(bank_code="FUBON", reason="credentials_wrong")`，不再重抽 captcha

#### Scenario: LLM fallback 啟用且 OCR 失敗時被呼叫

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=1`，OCR 回 `None`
- **THEN** `fetch_pdf()` SHALL 呼叫 `captcha_llm.solve_with_llm(jpeg)`，成功則用回傳值作為 `captcha_answer` 嘗試 `doLogin`

#### Scenario: LLM fallback 未啟用時 anthropic 不被 import

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=0` 且執行完整 `fetch_pdf` flow
- **THEN** `sys.modules` SHALL NOT 包含 `anthropic` 模組
