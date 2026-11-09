# agent-query-errors Specification

## Purpose
REST、MCP 與 CLI 回報 Agent 查詢錯誤的共同規則：錯誤只能以封閉的錯誤種類建立、對外訊息由範本產生且只允許呼叫端的整數識別、同一失敗在各 adapter 得到相同投影，以及非預期失敗的統一訊息。由 change deepen-agent-query-errors 建立。

## Requirements
### Requirement: Agent 查詢錯誤只能以封閉的錯誤種類建立
系統 SHALL 以一組封閉的錯誤種類建立 Agent 查詢錯誤。每個錯誤種類 SHALL 固定其 machine-readable `code`（`resource_not_found`、`invalid_argument`、`needs_human` 之一）、是否 `needs_human`，以及一個英文訊息範本。拋出錯誤的程式 SHALL 只能選擇錯誤種類並提供範本參數，SHALL NOT 自行提供訊息文字或附加資料。

#### Scenario: 公開訊息由範本產生
- **WHEN** 任一 service 以某個錯誤種類拋出 Agent 查詢錯誤
- **THEN** 對外的 `message` SHALL 等於該錯誤種類的範本套用參數後的結果
- **THEN** `code` 與 `needs_human` SHALL 由錯誤種類決定

#### Scenario: 新增錯誤不需維護額外的允許清單
- **WHEN** 開發者新增一個錯誤種類
- **THEN** 其訊息 SHALL 不需任何額外的允許清單設定即可對外顯示

### Requirement: 訊息參數只允許呼叫端提供的整數識別
範本參數 SHALL 只允許呼叫端提供的整數識別（例如帳單 id、pipeline run id），且 SHALL 限制在 12 位數以內；不得放入資料庫內容或任意字串（ADR-0001 第 5 點：secrets 永不跨越邊界）。參數超過 12 位數或不是整數時，訊息 SHALL 省略該識別，改用不含識別的範本。

#### Scenario: 一般帳單 id 會顯示
- **WHEN** Agent 查詢 `bill_id=123` 且該帳單不存在
- **THEN** `message` SHALL 為 `Bill #123 not found.`

#### Scenario: 類似卡號的識別不會回顯
- **WHEN** 呼叫端查詢識別為 `4111111111111111` 或非數字字串的 pipeline run，且該 run 不存在
- **THEN** `code` SHALL 為 `resource_not_found`
- **THEN** 回應中 SHALL NOT 出現該識別字串

#### Scenario: 找不到 pipeline run
- **WHEN** 呼叫端查詢 `run_id=42` 且該 run 不存在
- **THEN** `message` SHALL 為 `Pipeline run #42 not found.`

### Requirement: 三個 adapter 對同一失敗回傳相同投影
REST、MCP 與 CLI SHALL 透過同一個公開投影回傳 Agent 查詢錯誤：同一個 service 查詢的同一個失敗，在提供該查詢的每個 adapter 上 SHALL 得到相同的 `code`、`message` 與 `needs_human`。各 adapter 的外層格式維持不變：REST `{success, message, data}` 與狀態碼（404／422／500），MCP business-error envelope，CLI JSON 與 exit code 2。REST 在 FastAPI request validation 階段拒絕的參數（422 驗證 envelope）不屬於 Agent 查詢錯誤，維持既有行為。

#### Scenario: 不存在的帳單在 MCP 與 CLI 一致
- **WHEN** 以同一個不存在的帳單 id 分別呼叫 MCP `get_bill` 與 CLI `get-bill`
- **THEN** 兩者 SHALL 回傳相同的 `code=resource_not_found` 與 `message`（`Bill #999 not found.`）

#### Scenario: 不合法參數在 MCP 與 CLI 一致
- **WHEN** 以同一個不合法的月份分別呼叫 MCP `list_bills` 與 CLI `list-bills`
- **THEN** 兩者 SHALL 回傳相同的 `code=invalid_argument` 與相同的 `message`

#### Scenario: 資料庫內的格式錯誤資料在三個 adapter 一致
- **WHEN** 資料庫含格式錯誤的帳單月份，且分別呼叫 REST `GET /api/bills`、MCP `list_bills` 與 CLI `list-bills`
- **THEN** 三者 SHALL 回傳相同的 `code=needs_human`、`needs_human=true` 與相同的 `message`；REST 狀態碼為 500

### Requirement: 非預期失敗使用統一訊息
當查詢因非 Agent 查詢錯誤的例外而失敗時（例如資料庫錯誤），MCP、CLI 與 REST 的 Agent 查詢路由（bills、transactions、budgets、pipeline）SHALL 回傳相同的 `code=needs_human`、`needs_human=true` 與同一則訊息，且 SHALL NOT 回傳例外內容、SQL、連線資訊或 traceback。CLI MAY 另外在 stderr 輸出不含 secrets 的本機排查提示。

#### Scenario: 資料庫錯誤不外洩細節
- **WHEN** 查詢時資料庫拋出含 SQL 與參數的例外
- **THEN** 三個 adapter 回傳的 `message` SHALL 相同且不含該例外的任何內容
