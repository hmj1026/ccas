## ADDED Requirements

### Requirement: 共用例外階層以 `CcasError` 為基底
系統 SHALL 在 `core/exceptions.py` 定義 `CcasError(Exception)` 基底類別，以及各模組的專屬子類別，確保跨模組錯誤可被統一捕捉或精確區分。

#### Scenario: 可用基底類別統一捕捉所有 CCAS 例外
- **WHEN** pipeline 呼叫端以 `except CcasError` 捕捉例外
- **THEN** 由任一模組（ingestor、parser、classifier、notifier）拋出的例外均可被捕捉，不會有漏網的模組例外

#### Scenario: 可用子類別精確捕捉特定模組例外
- **WHEN** 呼叫端只需處理特定模組的錯誤（例如 `except DecryptError`）
- **THEN** 只有來自該模組的例外會被捕捉，其他模組的例外不受影響

#### Scenario: 例外攜帶可選的結構化 context 欄位
- **WHEN** 模組拋出例外時傳入 `context` 參數（例如附件路徑、銀行代碼）
- **THEN** 捕捉端可從 `context` 取得結構化診斷資訊，用於日誌記錄或錯誤回報

### Requirement: 結構化日誌輸出 JSON 格式
系統 SHALL 使用 Python stdlib `logging` 模組搭配自訂 `JsonFormatter`，輸出包含必要欄位的 JSON 格式日誌，以利後續接入 log aggregation 工具。

#### Scenario: 日誌記錄包含必要的結構化欄位
- **WHEN** 任何模組透過 `logging.getLogger(__name__)` 輸出日誌
- **THEN** 每一條日誌記錄應為合法的 JSON 物件，包含 `timestamp`、`level`、`logger`、`message` 欄位

#### Scenario: 各模組使用模組層級 logger
- **WHEN** 某模組呼叫 `logging.getLogger(__name__)`
- **THEN** 日誌記錄的 `logger` 欄位應反映該模組的完整路徑（例如 `ingestor.service`）

### Requirement: 日誌輸出不包含機敏資訊
系統 SHALL 在所有日誌輸出進入 handler 之前，自動遮罩符合機敏模式的欄位值，確保 OAuth token、密碼與 credentials 路徑不會出現在日誌記錄中。

#### Scenario: OAuth token 值在日誌中被遮罩
- **WHEN** 日誌訊息中包含 OAuth access token 或 refresh token 的實際值
- **THEN** 輸出的日誌記錄應將該值替換為 `[REDACTED]`，不顯示原始 token

#### Scenario: 密碼與 credentials 路徑在日誌中被遮罩
- **WHEN** 日誌訊息中包含密碼欄位值或本地 credentials 檔案完整路徑
- **THEN** 輸出的日誌記錄應將對應值替換為 `[REDACTED]`

#### Scenario: 不含機敏資訊的日誌正常輸出
- **WHEN** 日誌訊息不包含任何已定義的機敏模式
- **THEN** 訊息內容應保持原樣，不被遮罩修改

### Requirement: 日誌等級與格式可透過 Settings 設定
系統 SHALL 從 `Settings` 讀取 `log_level` 與 `log_format` 欄位，並在應用程式啟動時套用至 root logger，確保日誌行為可在不修改程式碼的情況下調整。

#### Scenario: 從 Settings 套用指定的日誌等級
- **WHEN** `Settings.log_level` 設為 `"DEBUG"`
- **THEN** DEBUG 等級及以上的日誌記錄均應輸出，不被過濾

#### Scenario: 使用預設值確保安全啟動
- **WHEN** `Settings` 中未明確設定 `log_level` 或 `log_format`
- **THEN** 系統應以 `"INFO"` 等級與 `"json"` 格式作為預設值正常啟動
