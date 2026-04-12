## MODIFIED Requirements

### Requirement: 使用者操作手冊涵蓋完整使用流程

系統 SHALL 提供 `docs/user-guide.md`，面向非開發者使用者，涵蓋從環境設定到日常操作的完整流程，每個步驟附完整可執行指令。依文件操作的使用者 MUST NOT 被要求手動 seed 資料庫內容——首次 `docker compose up` 必須讓 pipeline 立即可跑。

#### Scenario: 使用者依文件完成首次設定

- **WHEN** 使用者依照 `docs/user-guide.md` 的步驟操作
- **THEN** 文件 SHALL 引導使用者完成：`.env` 建立、Gmail 憑證設定、Telegram Bot 設定、Docker Compose 啟動，每步附完整指令

#### Scenario: 使用者執行 pipeline

- **WHEN** 使用者需要手動執行 pipeline
- **THEN** 文件 SHALL 提供 pipeline 執行指令，包括完整範例（全量執行、指定銀行、指定階段）

#### Scenario: 故障排除

- **WHEN** 使用者遇到常見問題（服務未啟動、parse 失敗、通知未送達）
- **THEN** 文件 SHALL 包含故障排除章節，列出症狀、原因、解決指令

#### Scenario: 首次執行 pipeline 無需手動 seed 銀行設定

- **WHEN** 使用者在全新 clone 的倉庫執行 `docker compose up -d` 後，緊接著跑 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --to ingest`
- **THEN** 該指令 SHALL NOT 因 `bank_configs` 表為空而失敗，使用者也 SHALL NOT 被要求先執行 `scripts/setup.sh` 或其他手動 seed 步驟

#### Scenario: 故障排除涵蓋 bank_configs 重新 seed

- **WHEN** 使用者需要重新載入 `banks.yaml` 變更
- **THEN** 故障排除章節 SHALL 指引使用者執行 `docker compose restart backend` 或手動 `docker exec ccas-backend-1 uv run python -m ccas.tools.bank_configs --apply`
