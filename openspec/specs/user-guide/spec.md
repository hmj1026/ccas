# user-guide Specification

## Purpose
TBD - created by archiving change local-ops-overhaul. Update Purpose after archive.
## Requirements
### Requirement: 使用者操作手冊涵蓋完整使用流程

系統 SHALL 提供 `docs/user-guide.md`，面向非開發者使用者，涵蓋從環境設定到日常操作的完整流程，每個步驟附完整可執行指令。

#### Scenario: 使用者依文件完成首次設定

- **WHEN** 使用者依照 `docs/user-guide.md` 的步驟操作
- **THEN** 文件 SHALL 引導使用者完成：`.env` 建立、Gmail 憑證設定、Telegram Bot 設定、Docker Compose 啟動，每步附完整指令

#### Scenario: 使用者執行 pipeline

- **WHEN** 使用者需要手動執行 pipeline
- **THEN** 文件 SHALL 提供 pipeline 執行指令，包括完整範例（全量執行、指定銀行、指定階段）

#### Scenario: 故障排除

- **WHEN** 使用者遇到常見問題（服務未啟動、parse 失敗、通知未送達）
- **THEN** 文件 SHALL 包含故障排除章節，列出症狀、原因、解決指令

### Requirement: 刪除 beginner-setup-guide.md

系統 SHALL 刪除 `docs/beginner-setup-guide.md`，其內容由 `docs/user-guide.md` 和 `docs/developer-guide.md` 取代。

#### Scenario: 舊文件不再存在

- **WHEN** 變更完成後
- **THEN** `docs/beginner-setup-guide.md` SHALL 不存在於專案中，`CLAUDE.md` 中的引用 SHALL 更新為新文件路徑

