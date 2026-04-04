## MODIFIED Requirements

### Requirement: Setup script orchestration

系統 SHALL 提供 `scripts/setup.sh`，一次性完成本機初始化。

腳本 MUST 使用 `set -euo pipefail`，任何步驟失敗立即停止並輸出明確錯誤訊息。

腳本 SHALL 依序執行：環境變數檢查、credentials 檢查、依賴安裝、Gmail token 產生、DB migration、bank config 同步（先 dry-run 再 apply）。

`TELEGRAM_CHAT_ID` 和 `TELEGRAM_ALLOWED_CHAT_IDS` 為選填設定。若未設定，腳本 SHALL 繼續執行並輸出警告，說明 notify stage 將無法發送 Telegram 通知。其他所有必要變數（`API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `GMAIL_CREDENTIALS_PATH` 等）仍為強制項。

#### Scenario: 缺少 .env 檔案
- **WHEN** 專案根目錄無 .env
- **THEN** 腳本立即停止，輸出提示使用者從 .env.example 複製

#### Scenario: 缺少 pipeline 必要環境變數
- **WHEN** .env 缺少 `API_TOKEN`、`TELEGRAM_BOT_TOKEN` 或 `GMAIL_CREDENTIALS_PATH`
- **THEN** 腳本立即停止，輸出缺少的變數名稱與修正建議

#### Scenario: TELEGRAM_CHAT_ID 未設定
- **WHEN** `TELEGRAM_CHAT_ID` 為空或未設定
- **THEN** 腳本 SHALL 輸出 `[WARN] TELEGRAM_CHAT_ID 未設定：notify stage 將無法發送 Telegram 通知，其他 stage 不受影響` 並繼續執行

#### Scenario: TELEGRAM_ALLOWED_CHAT_IDS 未設定
- **WHEN** `TELEGRAM_ALLOWED_CHAT_IDS` 為空或未設定
- **THEN** 腳本 SHALL 輸出 `[WARN] TELEGRAM_ALLOWED_CHAT_IDS 未設定：Telegram Bot 命令功能將受限` 並繼續執行

#### Scenario: 完整初始化成功
- **WHEN** 所有前置條件滿足
- **THEN** 依序完成所有步驟，輸出 [OK] 與下一步指示
