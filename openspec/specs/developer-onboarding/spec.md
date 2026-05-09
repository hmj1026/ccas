# developer-onboarding Specification

## Purpose
TBD - created by archiving change developer-onboarding. Update Purpose after archive.
## Requirements
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

系統 SHALL 維護 `config/bank-code-registry.yaml` 作為有效 `bank_code` 的唯一權威來源，並為每筆記錄提供 `fsc_code`。

Registry 每筆記錄 MUST 包含 `bank_code`、`bank_name`、`fsc_code`，可選 `supported` 和 `notes`。

`fsc_code` MUST 為三位數字字串，保留前導零。

Registry SHALL 至少涵蓋以下銀行代碼：CTBC, CATHAY, ESUN, TAISHIN, FUBON, MEGA, FIRST, SINOPAC, UBOT, HSBC, SCB, LANDBANK, TCB, HUANAN, CHANG_HWA, YUANTA。

#### Scenario: 載入擴充後的 registry

- **WHEN** 使用 `ccas.tools.bank_configs.load_bank_registry()` 載入更新後的 registry
- **THEN** 會回傳包含上述銀行代碼的 lookup dict，且每筆 `BankRegistryEntry` 皆可提供 `fsc_code`

#### Scenario: fsc_code 缺漏或格式錯誤

- **WHEN** registry 某筆記錄缺少 `fsc_code`，或其值不是三位數字字串
- **THEN** `load_bank_registry()` SHALL 拋出 `BankConfigValidationError`

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

### Requirement: Setup script 檢查 Tesseract OCR 相依性
`scripts/setup.sh` SHALL 在安裝後端依賴後，檢查 Tesseract 和 `chi_tra` Traditional Chinese 語言包是否已安裝，若未安裝則輸出明確的安裝指引並停止。

#### Scenario: Tesseract 未安裝
- **WHEN** `tesseract` 指令不在 PATH 中
- **THEN** 腳本 SHALL 停止並輸出 `[ERROR] 需要 tesseract OCR。請執行: brew install tesseract`

#### Scenario: chi_tra 語言包未安裝
- **WHEN** `tesseract` 已安裝但 `/opt/homebrew/share/tessdata/chi_tra.traineddata` 不存在
- **THEN** 腳本 SHALL 停止並輸出 `[ERROR] 需要 Tesseract Traditional Chinese 語言包。請執行: brew install tesseract-lang`

#### Scenario: Tesseract 和語言包均已安裝
- **WHEN** `tesseract` 可執行且 `chi_tra.traineddata` 存在
- **THEN** 腳本 SHALL 繼續執行後續步驟

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

系統 SHALL 提供 `docs/bank-codes.md` 銀行代碼對照表，並與 `config/bank-code-registry.yaml` 維持同步。

文件對照表 MUST 包含 `fsc_code` 欄位。

文件 SHALL 包含「已合併/停止發卡」區段，說明花旗銀行消金業務併入星展銀行等歷史變更。

#### Scenario: 所有 registry 銀行出現在文件中

- **WHEN** 比對 registry 與 `docs/bank-codes.md`
- **THEN** 每筆 registry 中的銀行 SHALL 在文件對照表中有對應列

#### Scenario: 使用者查詢花旗銀行

- **WHEN** 使用者在文件中搜尋「花旗」
- **THEN** SHALL 找到花旗消金業務已於 2023 年併入星展銀行的說明

### Requirement: Log persistence variables in .env.example

`.env.example` SHALL 文件說明日誌持久化相關環境變數。

#### Scenario: .env.example documents LOG_DIR

- **WHEN** 開發者查閱 `.env.example`
- **THEN** 可看到 `LOG_DIR`、`LOG_FILE_MAX_BYTES`、`LOG_FILE_BACKUP_COUNT`、`LOG_FILE_PREFIX` 的說明與預設值

### Requirement: Development tools documentation

開發者文件 SHALL 包含 GUI 工具的使用說明章節，涵蓋：

1. 可用的 GUI 工具清單與用途
2. 各工具的存取 URL
3. redis-commander 連線確認方式
4. 常見問題排解（port 衝突、資料庫檔案不存在）

#### Scenario: 開發者查閱 GUI 工具說明

- **WHEN** 開發者開啟開發文件
- **THEN** 可找到 SQLite Web GUI 和 redis-commander 的存取方式與啟動指令

#### Scenario: Port 衝突處理

- **WHEN** 預設 port 與其他本地服務衝突
- **THEN** 文件提供修改 port 映射的方法說明

