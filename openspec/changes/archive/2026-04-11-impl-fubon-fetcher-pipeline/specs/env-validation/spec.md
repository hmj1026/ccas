## ADDED Requirements

### Requirement: FUBON 專屬環境變數分級與格式驗證

`.env.example` SHALL 將以下 FUBON 專屬變數標示為「可選」（沒設時 FUBON fetcher 會明確跳過，不影響其他銀行）：`FUBON_ID_NUMBER`、`FUBON_BIRTHDAY`、`FUBON_CAPTCHA_MAX_RETRIES`、`FUBON_CAPTCHA_FALLBACK_LLM`。當任一變數被設定時，`Settings` pydantic validator SHALL 強制檢查格式。

#### Scenario: 未設定 FUBON credentials 不影響 check-env.sh 通過

- **WHEN** `.env` 完全沒有任何 `FUBON_*` 變數但所有必要變數齊全
- **THEN** `scripts/check-env.sh` SHALL 以 exit code 0 通過，並在可選變數警告區列出 `FUBON_ID_NUMBER`、`FUBON_BIRTHDAY` 為「未設定 → FUBON 自動下載停用」

#### Scenario: FUBON_ID_NUMBER 格式錯誤

- **WHEN** `FUBON_ID_NUMBER=abc12345` 或其他不符 `^[A-Z][12]\d{8}$` 的值
- **THEN** `Settings` 建立 SHALL raise `ValueError`，訊息包含 `FUBON_ID_NUMBER must be 10 chars`

#### Scenario: FUBON_BIRTHDAY 格式錯誤

- **WHEN** `FUBON_BIRTHDAY=1985-01-01`（西元格式，不是民國 7 碼）
- **THEN** `Settings` 建立 SHALL raise `ValueError`，訊息包含 `FUBON_BIRTHDAY must be ROC 7 digits`

#### Scenario: FUBON_CAPTCHA_MAX_RETRIES 預設值

- **WHEN** `.env` 沒設 `FUBON_CAPTCHA_MAX_RETRIES`
- **THEN** `Settings.fubon_captcha_max_retries` SHALL 為 `7`

#### Scenario: FUBON_CAPTCHA_FALLBACK_LLM 預設關閉

- **WHEN** `.env` 沒設 `FUBON_CAPTCHA_FALLBACK_LLM`
- **THEN** `Settings.fubon_captcha_fallback_llm` SHALL 為 `False`

#### Scenario: FUBON_CAPTCHA_FALLBACK_LLM 開啟但 anthropic 未安裝

- **WHEN** `FUBON_CAPTCHA_FALLBACK_LLM=1` 且 `anthropic` SDK 未安裝（未裝 `fubon-llm` extra）
- **THEN** `FubonFetcher.fetch_pdf()` 首次被呼叫時 SHALL raise `FetchError(reason="llm_fallback_sdk_missing")`
