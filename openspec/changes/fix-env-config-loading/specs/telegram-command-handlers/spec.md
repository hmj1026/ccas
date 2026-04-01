## MODIFIED Requirements

### Requirement: 僅回應白名單 chat_id
系統 SHALL 僅處理來自白名單 chat_id 的指令與訊息，非白名單來源靜默忽略。白名單 SHALL 從 `Settings.telegram_allowed_chat_ids` 欄位載入（透過 pydantic-settings 從 `.env` 或環境變數取得），而非直接讀取 `os.environ`。

`load_allowed_chat_ids()` SHALL 接受一個 `raw: str` 參數（逗號分隔的 chat_id 字串），解析後回傳 `frozenset[int]`。

#### Scenario: 白名單使用者正常使用指令
- **WHEN** 白名單中的使用者送出任何指令
- **THEN** bot 正常處理並回覆

#### Scenario: 非白名單使用者被靜默忽略
- **WHEN** 非白名單的 chat_id 送出任何訊息或指令
- **THEN** bot 不回覆任何內容，不記錄為錯誤

#### Scenario: 從 Settings 載入白名單
- **WHEN** `Settings.telegram_allowed_chat_ids` 為 `"111,222,333"`
- **THEN** `load_allowed_chat_ids("111,222,333")` 回傳 `frozenset({111, 222, 333})`

#### Scenario: 空白名單
- **WHEN** `Settings.telegram_allowed_chat_ids` 為空字串
- **THEN** `load_allowed_chat_ids("")` 回傳空 `frozenset()`
