# user-guide Specification

## Purpose
TBD - created by archiving change local-ops-overhaul. Update Purpose after archive.
## Requirements
### Requirement: 使用者操作手冊涵蓋完整使用流程

系統 SHALL 提供 `docs/user-guide.md`，面向非開發者使用者，涵蓋從環境設定到日常操作的完整流程，每個步驟附完整可執行指令。依文件操作的使用者 MUST NOT 被要求手動 seed 資料庫內容——首次 `docker compose up` 必須讓 pipeline 立即可跑且分類規則就緒。PDF 密碼設定章節 MUST 說明當舊期帳單解密失敗時，可透過 `PDF_PASSWORD_<BANK>_LEGACY_N` 設定額外的 legacy 密碼。FUBON 銀行因下載系統 SPA 遷移尚未完成自動化，文件 MUST 提供清晰的「手動放檔」步驟，讓使用者能在 pipeline 完成 FUBON 的完整處理。

#### Scenario: 使用者依文件完成首次設定

- **WHEN** 使用者依照 `docs/user-guide.md` 的步驟操作
- **THEN** 文件 SHALL 引導使用者完成：`.env` 建立、Gmail 憑證設定、Telegram Bot 設定、Docker Compose 啟動，每步附完整指令

#### Scenario: 使用者執行 pipeline

- **WHEN** 使用者需要手動執行 pipeline
- **THEN** 文件 SHALL 提供 pipeline 執行指令，包括完整範例（全量執行、指定銀行、指定階段）

#### Scenario: 故障排除

- **WHEN** 使用者遇到常見問題（服務未啟動、parse 失敗、通知未送達、分類全未分類）
- **THEN** 文件 SHALL 包含故障排除章節，列出症狀、原因、解決指令

#### Scenario: 故障排除涵蓋 categories 重新 seed

- **WHEN** 使用者需要重新載入 `categories.yaml` 變更或發現分類全部為「未分類」
- **THEN** 故障排除章節 SHALL 指引使用者執行 `docker compose restart backend` 或手動 `docker exec ccas-backend-1 uv run python -m ccas.tools.categories --apply`，並說明 YAML 為 SSOT 的覆寫行為

#### Scenario: PDF 密碼章節涵蓋 legacy 密碼

- **WHEN** 使用者設定 `PDF_PASSWORD_<BANK>` 後仍有舊期帳單解密失敗
- **THEN** 文件 SHALL 指引使用者新增 `PDF_PASSWORD_<BANK>_LEGACY_1` 至 `_LEGACY_5` 來提供歷史密碼，並說明解密會按 primary → legacy_1 → ... 順序嘗試

#### Scenario: FUBON 手動下載步驟

- **WHEN** 使用者需要處理 FUBON 帳單
- **THEN** 文件 SHALL 包含「從富邦網銀手動下載 PDF → 放入 `backend/data/manual-staging/FUBON/` → 執行 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON`」的完整步驟，並說明檔名含 `YYYY-MM` 月份可協助自動配對

### Requirement: 刪除 beginner-setup-guide.md

系統 SHALL 刪除 `docs/beginner-setup-guide.md`，其內容由 `docs/user-guide.md` 和 `docs/developer-guide.md` 取代。

#### Scenario: 舊文件不再存在

- **WHEN** 變更完成後
- **THEN** `docs/beginner-setup-guide.md` SHALL 不存在於專案中，`CLAUDE.md` 中的引用 SHALL 更新為新文件路徑

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

