## MODIFIED Requirements

### Requirement: 使用者操作手冊涵蓋完整使用流程

系統 SHALL 提供 `docs/user-guide.md`，面向非開發者使用者，涵蓋從環境設定到日常操作的完整流程，每個步驟附完整可執行指令。FUBON 銀行因下載系統 SPA 遷移尚未完成自動化，文件 MUST 提供清晰的「手動放檔」步驟，讓使用者能在 pipeline 完成 FUBON 的完整處理。

#### Scenario: 使用者依文件完成首次設定

- **WHEN** 使用者依照 `docs/user-guide.md` 的步驟操作
- **THEN** 文件 SHALL 引導使用者完成 `.env` 建立、憑證設定、Docker Compose 啟動等步驟

#### Scenario: 使用者執行 pipeline

- **WHEN** 使用者需要手動執行 pipeline
- **THEN** 文件 SHALL 提供 pipeline 執行指令，包括完整範例

#### Scenario: 故障排除

- **WHEN** 使用者遇到常見問題
- **THEN** 文件 SHALL 包含故障排除章節

#### Scenario: FUBON 手動下載步驟

- **WHEN** 使用者需要處理 FUBON 帳單
- **THEN** 文件 SHALL 包含「從富邦網銀手動下載 PDF → 放入 `backend/data/manual-staging/FUBON/` → 執行 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank FUBON`」的完整步驟，並說明檔名含 `YYYY-MM` 月份可協助自動配對
