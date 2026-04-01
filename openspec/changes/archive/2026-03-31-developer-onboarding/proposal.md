## Why

新開發者第一次 clone CCAS 後，需要手動完成 Gmail OAuth、Telegram Bot 設定、bank_configs 資料庫寫入、環境變數檢查等多個步驟，容易遺漏且錯誤訊息不明確。需要一套 CLI 工具與腳本，將初始化流程自動化並提供明確的錯誤指引。

## What Changes

- 新增 `ccas.tools.gmail_auth` CLI 工具：驗證 credentials 路徑、執行 OAuth 授權、產生本地 `token.json`
- 新增 `ccas.tools.bank_configs` CLI 工具：從 `config/banks.yaml` 載入銀行設定，對照 `config/bank-code-registry.yaml` 驗證，同步到資料庫（支援 dry-run）
- 新增 `config/bank-code-registry.yaml`：銀行代碼主檔，作為 bank_code 的唯一權威來源
- 新增 `config/banks.example.yaml`：銀行設定範本，供使用者複製後編輯
- 新增 `scripts/setup.sh`：一次性初始化腳本，串接環境檢查、依賴安裝、OAuth、migration、bank config 同步
- 新增 `scripts/start.sh`：日常啟動腳本，確認依賴後啟動 FastAPI dev server
- 新增 `docs/beginner-setup-guide.md`：完整的新手上手指南（從 clone 到前後端跑通）
- 新增 `docs/bank-codes.md`：銀行代碼對照表
- 更新 `.env.example`：新增 `TELEGRAM_ALLOWED_CHAT_IDS`，路徑改為相對路徑，新增前端 `VITE_` 變數
- 更新 `README.md`：新增新手指南連結，後端啟動改用腳本
- 新增 `pyyaml` 依賴

## Capabilities

### New Capabilities

- `developer-onboarding`: 開發者初始化工具與文件，涵蓋 Gmail OAuth CLI、bank config sync CLI、shell 腳本自動化、bank code registry、新手上手文件

### Modified Capabilities

（無既有 spec 的需求層級變更）

## Impact

- **新模組**: `backend/src/ccas/tools/` (gmail_auth.py, bank_configs.py)
- **新設定檔**: `config/bank-code-registry.yaml`, `config/banks.example.yaml`
- **新腳本**: `scripts/setup.sh`, `scripts/start.sh`
- **新文件**: `docs/beginner-setup-guide.md`, `docs/bank-codes.md`
- **依賴**: 新增 `pyyaml` runtime dependency
- **既有檔案**: `.env.example`, `README.md`, `backend/pyproject.toml` 有小幅更新
