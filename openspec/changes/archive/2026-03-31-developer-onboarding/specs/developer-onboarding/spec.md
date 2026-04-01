## ADDED Requirements

### Requirement: Gmail OAuth CLI tool

系統 SHALL 提供 `python -m ccas.tools.gmail_auth` CLI 工具，用於產生或更新本地 Gmail OAuth token。

工具 SHALL 接受以下參數：
- `--credentials`: credentials.json 路徑（預設讀取 Settings）
- `--token`: token.json 輸出路徑（預設讀取 Settings）
- `--force`: 強制重新授權，即使 token 已存在

工具 SHALL 在 credentials 路徑不存在時回傳 exit code 2 並輸出包含 `GMAIL_CREDENTIALS_PATH` 的錯誤訊息。

工具 SHALL 在 token 已存在且未指定 `--force` 時跳過授權並回傳 exit code 0。

#### Scenario: Credentials 檔案不存在
- **WHEN** 使用者執行 gmail_auth 但 credentials.json 不存在
- **THEN** 工具回傳 exit code 2，stderr 包含路徑與修正建議

#### Scenario: Token 已存在且無 force flag
- **WHEN** token.json 已存在且未指定 --force
- **THEN** 工具輸出 [SKIP] 訊息並回傳 exit code 0

#### Scenario: 首次授權成功
- **WHEN** credentials.json 存在且 token.json 不存在
- **THEN** 工具啟動 OAuth 流程，寫入 token.json，輸出 [OK] 訊息

#### Scenario: 強制重新授權
- **WHEN** 使用者指定 --force 且 token.json 已存在
- **THEN** 工具重新執行 OAuth 流程並覆寫 token.json

### Requirement: Bank code registry

系統 SHALL 維護 `config/bank-code-registry.yaml` 作為有效 bank_code 的唯一權威來源。

Registry 每筆記錄 MUST 包含 `bank_code`（大寫）和 `bank_name`，可選 `supported` 和 `notes`。

Registry MUST 禁止重複的 bank_code。

#### Scenario: 載入有效 registry
- **WHEN** registry YAML 包含有效的 banks 清單
- **THEN** 回傳以 bank_code 為 key 的 lookup dict

#### Scenario: Registry 包含重複 bank_code
- **WHEN** registry 有兩筆相同的 bank_code
- **THEN** 拋出 BankConfigValidationError 包含 "重複 bank_code"

#### Scenario: Registry 檔案不存在
- **WHEN** 指定路徑不存在
- **THEN** 拋出 BankConfigValidationError 包含 "找不到"

### Requirement: Bank config YAML validation

系統 SHALL 從 `config/banks.yaml` 載入銀行設定，並對照 bank-code-registry 驗證。

系統 SHALL 將小寫 bank_code 自動正規化為大寫。

每筆設定 MUST 包含 `bank_code` 和 `gmail_filter`。

`active_parser_version` 預設為 `"v1"`，`is_active` 預設為 `true`。

系統 MUST 拒絕不在 registry 中的 bank_code，錯誤訊息包含可用值清單。

系統 MUST 拒絕重複的 bank_code。

#### Scenario: 正規化小寫 bank_code
- **WHEN** banks.yaml 包含 bank_code: ctbc
- **THEN** 正規化為 CTBC 並從 registry 取得 bank_name

#### Scenario: 拒絕未知 bank_code
- **WHEN** banks.yaml 包含不在 registry 中的 bank_code
- **THEN** 拋出錯誤，訊息包含未知代碼與可用值清單

#### Scenario: 缺少 gmail_filter
- **WHEN** 某筆設定的 gmail_filter 為空
- **THEN** 拋出錯誤，訊息包含 "gmail_filter"

### Requirement: Bank config database sync

系統 SHALL 提供 `python -m ccas.tools.bank_configs` CLI 工具，將 YAML 設定同步到 BankConfig 資料表。

工具 SHALL 支援 upsert 語意：新增不存在的 row、更新已變更的 row、跳過未變更的 row。

工具 MUST 預設為 dry-run 模式，僅預覽變更內容。指定 `--apply` 才實際寫入。

工具 SHALL 回傳 SyncSummary，包含 created、updated、unchanged 計數與 actions 清單。

#### Scenario: 新增一筆 bank config
- **WHEN** YAML 包含一筆 DB 中不存在的 bank_code
- **THEN** summary.created = 1，actions 包含 "CREATE"

#### Scenario: 更新已變更的 bank config
- **WHEN** YAML 的 gmail_filter 與 DB 現有值不同
- **THEN** summary.updated = 1，DB row 更新為新值

#### Scenario: 跳過未變更的 bank config
- **WHEN** YAML 與 DB 完全一致
- **THEN** summary.unchanged = 1，actions 包含 "UNCHANGED"

#### Scenario: Dry-run 不寫入
- **WHEN** 未指定 --apply
- **THEN** 不呼叫 session.commit()，呼叫 session.rollback()

### Requirement: Setup script orchestration

系統 SHALL 提供 `scripts/setup.sh`，一次性完成本機初始化。

腳本 MUST 使用 `set -euo pipefail`，任何步驟失敗立即停止並輸出明確錯誤訊息。

腳本 SHALL 依序執行：環境變數檢查、credentials 檢查、依賴安裝、Gmail token 產生、DB migration、bank config 同步（先 dry-run 再 apply）。

#### Scenario: 缺少 .env 檔案
- **WHEN** 專案根目錄無 .env
- **THEN** 腳本立即停止，輸出提示使用者從 .env.example 複製

#### Scenario: 缺少必要環境變數
- **WHEN** .env 缺少 API_TOKEN 等必要變數
- **THEN** 腳本立即停止，輸出缺少的變數名稱與修正建議

#### Scenario: 完整初始化成功
- **WHEN** 所有前置條件滿足
- **THEN** 依序完成所有步驟，輸出 [OK] 與下一步指示

### Requirement: Start script

系統 SHALL 提供 `scripts/start.sh`，用於日常啟動後端 API。

腳本 SHALL 確認依賴後啟動 FastAPI dev server（uvicorn, host=127.0.0.1, port=8000, reload）。

#### Scenario: 正常啟動
- **WHEN** .env 存在且 API_TOKEN 已設定
- **THEN** 執行 uv sync、alembic upgrade head、啟動 uvicorn

#### Scenario: 缺少 .env
- **WHEN** .env 不存在
- **THEN** 腳本停止，提示先執行 setup.sh

### Requirement: Onboarding documentation

系統 SHALL 提供 `docs/beginner-setup-guide.md` 新手指南，涵蓋從零到前後端跑通的完整流程。

系統 SHALL 提供 `docs/bank-codes.md` 銀行代碼對照表。

文件 MUST 與實際程式碼行為一致（環境變數名稱、路徑、指令）。

#### Scenario: 新手依照指南完成設定
- **WHEN** 使用者照著指南從第 1 步執行到最後
- **THEN** 成功完成 Gmail OAuth、Telegram Bot 設定、後端啟動、前端啟動、Telegram 測試訊息

#### Scenario: 文件引用正確的環境變數來源
- **WHEN** 文件提及前端環境變數
- **THEN** 指向根目錄 `.env` 的 `VITE_` 前綴變數（非 frontend/.env.local）
