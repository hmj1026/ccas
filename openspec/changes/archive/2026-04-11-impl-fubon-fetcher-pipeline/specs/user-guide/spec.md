## ADDED Requirements

### Requirement: user-guide SHALL 說明 FUBON 自動下載設定與免責聲明

`docs/user-guide.md` 的 FUBON 章節 SHALL 包含：(1) 四個 FUBON 專屬 env vars 的用途與格式範例；(2) 法遵免責聲明，明確說明自動化流程僅處理使用者本人的郵件與本人的 credentials，屬使用者授權代理；(3) 未設定 credentials 時的降級行為（fetcher 明確 raise `FetchError`，其他銀行不受影響）；(4) captcha OCR 失敗時的排障步驟（檢查日誌 `captcha_retry_exhausted` → 啟用 LLM fallback 或切換 manual staging）。

#### Scenario: FUBON 章節提到必填 env vars

- **WHEN** 讀者閱讀 `docs/user-guide.md` 的 FUBON 章節
- **THEN** 章節 SHALL 列出 `FUBON_ID_NUMBER`（格式 `[A-Z][12]\d{8}`）與 `FUBON_BIRTHDAY`（民國 7 碼），並提供範例

#### Scenario: 免責聲明包含三要素

- **WHEN** 讀者閱讀 FUBON 章節的「免責聲明」小節
- **THEN** 該小節 SHALL 同時包含：「使用者本人郵件」、「使用者本人身分證號」、「使用者授權代理」三個關鍵詞

#### Scenario: 排障章節涵蓋 captcha_retry_exhausted

- **WHEN** 讀者 grep 文件中 `captcha_retry_exhausted`
- **THEN** 文件 SHALL 出現該錯誤字串，並提供至少兩個可能的解法（啟用 LLM fallback、切換 manual staging）
