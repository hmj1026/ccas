# agent-mcp-interface Specification

## Purpose
TBD - created by archiving change add-agent-mcp-interface. Update Purpose after archive.
## Requirements
### Requirement: MCP 使用現行協定版本、探索與能力宣告

系統 SHALL 以 MCP `2026-07-28` 現行協定作為 wire contract。Server SHALL 實作 `server/discover`，讓 client 在任何其他 MCP request 前取得 `supportedVersions`、`capabilities` 與 server identity。Server SHALL 宣告 `capabilities.tools`；除非實作工具清單變更通知，否則不得宣告 `tools.listChanged`。`server/discover` 與後續 request SHALL 使用 JSON-RPC 2.0，且每個 modern request 的 `_meta` SHALL 包含 `io.modelcontextprotocol/protocolVersion` 與 `io.modelcontextprotocol/clientCapabilities`；`io.modelcontextprotocol/clientInfo` 為 optional，CCAS 自有 client SHOULD 提供但 server 不得因缺少它而拒絕合法 request。Discovery response 的 server identity SHALL 放在 `result._meta["io.modelcontextprotocol/serverInfo"]`，不得放成自訂的頂層 `serverInfo`。

所有包含 `result` 的 JSON-RPC result（包含 discovery、`tools/list`、`tools/call` 的成功或 tool execution failure result）SHALL 包含 `resultType="complete"`；本 change 不使用 `input_required`。JSON-RPC protocol error 沒有 `result`，因此不適用 `resultType`。若 SDK 同時支援舊版 client，client SHALL 只在 discovery 回傳其他錯誤或合理逾時／無回應時 fallback 到 legacy `initialize`；若收到 `UnsupportedProtocolVersionError`，代表對端是 modern server，client 應改選 `supportedVersions` 中的版本，不得 fallback 到 `initialize`。本 change 不得把 legacy `initialize` 當成現行協定唯一的 handshake。Server 收到不支援的協定版本時 SHALL 回報 `UnsupportedProtocolVersionError`，且不得執行該 request 的工具副作用。

#### Scenario: 現代 client 先完成 server discovery

- **WHEN** client 以目標協定版本呼叫 `server/discover`
- **THEN** server SHALL 回傳 `resultType="complete"`、`supportedVersions`、`capabilities.tools` 與 `result._meta["io.modelcontextprotocol/serverInfo"].name`／`.version`，並允許 client 再呼叫 `tools/list`

#### Scenario: 不支援的協定版本不執行工具

- **WHEN** client 在 request metadata 宣告 server 不支援的協定版本
- **THEN** server SHALL 回傳 `UnsupportedProtocolVersionError`，不得呼叫 service、寫入資料或把 request 當成成功處理

### Requirement: 工具清單與 schema 必須可被 MCP client 驗證

`tools/list` SHALL 回傳六個唯讀工具：`list_bills`、`get_bill`、`query_transactions`、`get_payment_due`、`budget_status`、`pipeline_status`。每個 tool definition SHALL 包含穩定的 `name`、面向 Agent 的 `description`、有效的 JSON Schema `inputSchema`，以及描述 structured result 的 `outputSchema`；工具清單 SHALL 使用 deterministic order。六個唯讀工具 SHOULD 將 annotation 設為 `readOnlyHint=true`、`destructiveHint=false`、`idempotentHint=true`；annotations 只是提示，不得取代授權與輸入驗證。

`inputSchema` SHALL 明確列出各工具可接受的欄位、型別、必要欄位、上下限與額外欄位策略；列表工具的業務分頁 cursor SHALL 與 MCP `tools/list` 的 protocol cursor 分開，不得混用。`outputSchema` SHALL 與共用 Agent DTO 保持同步，不能只在 description 內以自然語言描述欄位。`tools/list` 的 JSON-RPC result SHALL 包含 `resultType="complete"`。

本 change 的 canonical tool input 如下；除表中列出的 optional properties 外，`inputSchema` SHALL 設 `additionalProperties=false`。`month` 存在時優先於 `year`；`get_bill` 的 `bill_id` 是 CCAS DB identity，對帳用的 `reconciliation_key` 只作為 output 欄位，不取代 `bill_id` 查詢。

| Tool | Input properties | 行為邊界 |
|---|---|---|
| `list_bills` | `month?: string`（`YYYY-MM`）、`year?: integer`（2000–2099）、`bank_code?: string`、`status?: "all"\|"paid"\|"unpaid"`（default `all`）、`page?: integer`（≥1，default 1）、`page_size?: integer`（1–100，default 20） | 沿用 bills API 篩選與排序語意 |
| `get_bill` | `bill_id: integer`（≥1） | 找不到時使用 `resource_not_found`，不得以 reconciliation key 猜測另一筆帳單 |
| `query_transactions` | `month?: string`、`year?: integer`（2000–2099）、`bank_code?: string`、`category?: string`、`q?: string`（至少 2 字元）、`sort?: "trans_date_asc"\|"trans_date_desc"\|"amount_asc"\|"amount_desc"\|"merchant_asc"\|"merchant_desc"`（default `trans_date_desc`）、`page?: integer`（≥1，default 1）、`page_size?: integer`（1–100，default 20） | 沿用 transactions API 篩選、排序與分頁語意 |
| `get_payment_due` | `{}` | 回傳所有未繳帳單的到期彙總，依 `due_date` 由近到遠排序；不得要求 `run_id` |
| `budget_status` | `scope?: "monthly_total"\|"monthly_category"\|"monthly_bank"`、`include_current_period?: boolean`（default `false`） | 沿用 budgets API 的 scope 與 current-period 語意 |
| `pipeline_status` | `{}` | 只查最近一次執行；不得要求呼叫方先提供 `run_id` |

以下是本 change 的 canonical structured payload；欄位未標示 `?` 即為 required，`null` 表示可為 JSON null。這是六個工具的 project schema source，實作階段 SHALL 由 Agent Pydantic DTO 產生對應 `outputSchema`，不可另外發明欄位名稱。

| 型別 | 必要欄位與限制 |
|---|---|
| `Money` | `currency: "TWD"`、`value: string`（非 scientific notation 的 decimal string） |
| `PageMeta` | `page: integer >= 1`、`page_size: integer 1..100`、`total: integer >= 0`、`total_pages: integer >= 1`、`has_next: boolean` |
| `AgentBill` | `id: integer`、`bank_code: string`、`bank_name: string|null`、`billing_month: YYYY-MM string`、`total_amount: Money`、`due_date: date string`、`is_paid: boolean`、`created_at: date-time string`、`card_last4s: four-digit string[]`（去重排序，無卡為空陣列）、`reconciliation_key: string`；不得包含 `pdf_url` 或本機檔案路徑 |
| `AgentTransaction` | `id: integer`、`bill_id: integer`、`trans_date: date string`、`posting_date: date string|null`、`merchant: string`、`amount: Money`、`original_amount: Money|null`、`card_last4: four-digit string|null`、`category: string|null`、`bank_code: string`、`billing_month: YYYY-MM string`、`installment_current: integer|null`、`installment_total: integer|null`、`reconciliation_key: string` |
| `BudgetCurrentPeriod` | `period_year_month: YYYY-MM string`、`amount: Money`、`current_amount: Money`、`percent: number`、`threshold_breached: boolean`、`alert_threshold_percent: integer 1..100` |
| `BudgetStatus` | `id: integer`、`scope: monthly_total\|monthly_category\|monthly_bank`、`scope_ref: string|null`、`amount: Money`、`alert_threshold_percent: integer 1..100`、`enabled: boolean`、`current_period: BudgetCurrentPeriod|null` |
| `PipelineStageSummary` | `stage: string`、`ok: integer >= 0`、`fail: integer >= 0`、`elapsed_ms: integer >= 0`、`counts: object<string, integer >= 0>`、`errors: string[]`；所有錯誤文字不得含 secrets |
| `PipelineStatus` | `id: string`、`job_id: string`、`status: queued\|running\|succeeded\|failed\|cancelled`、`triggered_by: string`、`params: object`（已脫敏）、`current_stage: string|null`、`current_stage_processed: integer >= 0`、`current_stage_total: integer >= 0`、`stage_summary: PipelineStageSummary[]`、`error_message: string|null`、`started_at: date-time string|null`、`completed_at: date-time string|null`、`created_at: date-time string`、`updated_at: date-time string`、`needs_human: boolean` |

六個工具的成功 `structuredContent` SHALL 使用以下 envelope：`list_bills` 為 `{data: AgentBill[], pagination: PageMeta}`、`get_bill` 為 `{data: AgentBill}`、`query_transactions` 為 `{data: AgentTransaction[], pagination: PageMeta}`、`get_payment_due` 為 `{data: AgentBill[]}`、`budget_status` 為 `{data: BudgetStatus[]}`、`pipeline_status` 為 `{data: PipelineStatus}`。Tool execution error 使用本文件定義的共用 error envelope，不把它塞進成功 DTO。

#### Scenario: client 列出六個可驗證的讀取工具

- **WHEN** client 完成 discovery 後呼叫 `tools/list`
- **THEN** 回應 SHALL 包含 `resultType="complete"`，只包含本 change 的六個讀取工具，且每個 definition 都能通過 JSON Schema 驗證；未實作 `listChanged` notification 時，工具清單 SHALL 不宣告該能力

#### Scenario: 不合法輸入在 service 前被拒絕

- **WHEN** Agent 傳入缺少必要欄位、型別錯誤、超出限制或 schema 不允許的欄位
- **THEN** MCP server SHALL 先依 `inputSchema` 驗證並回傳明確的工具執行錯誤，不得以猜測、靜默忽略或部分套用的參數呼叫 service

### Requirement: Tool result 同時提供相容文字與 structured content

成功的工具呼叫 SHALL 回傳 MCP `content`，並在有 `outputSchema` 的工具中回傳符合該 schema 的 `structuredContent`。為相容未讀取 structured content 的 client，回傳 structured result 的工具 SHOULD 同時在 `content` 包含一個序列化後的 JSON `TextContent`；該文字內容 SHALL 與 `structuredContent` 表示同一份資料，不得另外形成第二套欄位契約。

#### Scenario: 成功結果可由 schema 與舊 client 共同讀取

- **WHEN** Agent 以合法參數呼叫任一讀取工具且查詢成功
- **THEN** 回應的 `resultType` SHALL 是 `complete`，並通過該工具的 `outputSchema` 驗證；`content`／`structuredContent` 的欄位、數值與排序 SHALL 一致

### Requirement: MCP protocol error 與 tool execution error 分層

MCP server SHALL 將 malformed JSON-RPC、未知 method、未知 tool 或不符合協定的 request 回傳標準 JSON-RPC protocol error；不得自訂一個與 JSON-RPC error code 混淆的業務錯誤碼。工具已被正確呼叫但業務執行失敗時，SHALL 回傳 MCP tool result 的 `resultType="complete"`、`isError=true`、可供人閱讀的 `content`，以及符合共用 Agent business-error envelope schema 的 `structuredContent`。不得在 tool definition 發明非 MCP 標準的 `errorSchema` 欄位；錯誤 envelope 是 implementation／contract schema，不是另一個 wire capability。

業務錯誤至少 SHALL 使用 `resource_not_found`、`invalid_argument`、`needs_human` 三種 machine-readable `code`；`needs_human` 是 tool result 的業務欄位，不是 JSON-RPC protocol error code。錯誤 `structuredContent` SHALL 通過共用 error envelope schema，且 `content` SHOULD 同時包含其序列化 JSON `TextContent`。錯誤回應同樣 SHALL 遵守 secrets contract，且不得把 exception traceback 或內部連線資訊回傳給 Agent。

共用 error envelope 至少 SHALL 是 `{ "code": "...", "message": "..." }`；`code` 只能使用已定義的 machine-readable 值，`message` SHALL 是不含 secrets 的可行動訊息。只有 `code=needs_human` 時才 SHALL 額外包含 `needs_human=true`；不得把完整 exception、SQL、token、檔案密碼或內部 host／path 放進 `message` 或任何可選 details。

#### Scenario: 不存在的資源是工具執行錯誤

- **WHEN** Agent 以合法 schema 呼叫 `get_bill`，但識別鍵不存在
- **THEN** server SHALL 回傳 `resultType="complete"`、`isError=true` 與 structured business error `code=resource_not_found`，不得回傳空物件偽裝成成功，也不得回傳 JSON-RPC protocol error 代替該業務結果

#### Scenario: pipeline 需要人工介入

- **WHEN** Agent 呼叫 `pipeline_status` 且最近一次執行處於需要人工處理的失敗狀態
- **THEN** server SHALL 回傳 `resultType="complete"`、`isError=true` 並在 structured business error 標示 `code=needs_human` 與 `needs_human=true`，同時提供不含 secrets 的可行動訊息

### Requirement: stdio stream 只承載 MCP JSON-RPC message

stdio MCP server SHALL 將每個 JSON-RPC request、notification 或 response 編碼為一個完整 JSON object，於 stdout 以單一 newline-delimited message 傳輸；message 內不得有 embedded newline。stdout 除 MCP message 外不得輸出 banner、debug、progress 或 traceback；診斷 log SHALL 使用 UTF-8 寫入 stderr。Server 收到 stdin EOF 時 SHALL 及時結束，不得等待不存在的後續輸入。

#### Scenario: stdout 不混入非協定輸出

- **WHEN** client 啟動 server 並完成 discovery、tools/list 與一次 tool call
- **THEN** client SHALL 能逐行解析 stdout 上的每個 MCP message；任何啟動訊息、debug log 或 exception traceback SHALL 不出現在 stdout

#### Scenario: stdin 關閉後 server 結束

- **WHEN** client 關閉 stdio server 的 stdin
- **THEN** server SHALL 在清理資源後及時退出，且不建立背景工作等待新的 request

### Requirement: MCP server 以 stdio transport 提供唯讀工具

系統 SHALL 提供一個以官方 `mcp` Python SDK 實作的 stdio MCP server，預設註冊 `list_bills`、`get_bill`、`query_transactions`、`get_payment_due`、`budget_status`、`pipeline_status` 六個唯讀工具，回傳值 SHALL 使用與 CLI 共用的 Agent Pydantic DTO 序列化；資料語意 SHALL 與既有 REST API（`bills-api`/`pipeline-operations-center`）一致，但不得因此改變既有 HTTP response shape。

#### Scenario: 同機 Agent 連線取得帳單列表

- **WHEN** 一個與 CCAS 同機執行的 Agent 透過 stdio 連上 MCP server 並呼叫 `list_bills`
- **THEN** 系統 SHALL 回傳結構化的帳單列表，欄位語意與 `GET /api/bills` 的 `BillItem` 一致，且金額以 Agent DTO 定義的明確幣別格式呈現

#### Scenario: 唯讀工具不受寫入開關阻擋

- **WHEN** Agent 呼叫任一唯讀工具，無論 `agent_write_enabled` 是 `False` 或 `True`
- **THEN** 系統 SHALL 正常回應，不因寫入開關關閉而拒絕唯讀請求

### Requirement: 列表型工具支援分頁

系統 SHALL 讓 `list_bills`、`query_transactions` 使用本文件 canonical input 定義的 `page`／`page_size` 分頁參數，並在回應的 `PageMeta.has_next` 包含是否還有下一頁的資訊。MCP `tools/list` 的 protocol cursor 只供工具清單分頁使用；本 change 的業務工具不接受 `limit`、`offset` 或另一套 cursor alias。

#### Scenario: 超過單頁上限的查詢

- **WHEN** Agent 呼叫 `query_transactions` 且符合條件的交易數超過單頁上限
- **THEN** 系統 SHALL 回傳該頁資料與可用於取得下一頁的分頁資訊，不得靜默截斷且不提示

### Requirement: 金額一律以明確幣別格式回傳

系統 SHALL 讓所有金額欄位以 `{ "currency": "TWD", "value": "<decimal-string>" }` 的形式回傳，不得回傳裸浮點數或未標示幣別的整數。本 change 不採用整數「分」表示；資料庫現況的整數「元」只可在 service adapter 內轉換後輸出，`value` SHALL 保留實際元值而非轉成分。

#### Scenario: 帳單金額格式

- **WHEN** Agent 呼叫 `get_bill` 取得帳單金額
- **THEN** 回應中的金額欄位 SHALL 是 `{ "currency": "TWD", "value": "..." }`，不得是不含幣別的浮點數或整數

### Requirement: 回應內容永不包含 secrets

系統 SHALL 保證任何 MCP 工具的回應內容都不包含 PDF 密碼、OAuth refresh token、session secret、或完整信用卡卡號；卡號欄位只 SHALL 回傳既有的末四碼。

#### Scenario: 帳單詳情不外洩卡號

- **WHEN** Agent 呼叫 `get_bill` 或 `query_transactions`
- **THEN** 回應中若含卡片資訊，只 SHALL 包含末四碼，不得包含完整卡號、密碼或 token 欄位

#### Scenario: 契約測試涵蓋全部唯讀工具

- **WHEN** 執行 secrets 洩漏的契約測試
- **THEN** 系統 SHALL 對六個唯讀工具的回應逐一斷言不含密碼／token／完整卡號欄位

### Requirement: 本 change 只註冊唯讀工具，寫入工具留給 Phase 3

本 change 的 MCP server SHALL 永遠只註冊六個唯讀工具；`agent_write_enabled`（預設 `False`）在本 change 只保留為 Phase 3 的本機可用性契約，無論設定為何都不得讓未完成 schema、錯誤、授權與副作用契約的寫入工具出現在 `tools/list`。Phase 3 若要註冊 `mark_bill_paid`、`set_payment_status`、`override_transaction_category`、`trigger_ingest` 或 `retry_parse`，必須另以完整 OpenSpec change 定義每個 tool 的 `inputSchema`、`outputSchema`、`isError` mapping、使用者明確授權與 mutation tests；`agent_write_enabled=True` 永遠不等於任何一次寫入授權。

#### Scenario: 任何設定下本 change 都不宣告寫入工具

- **WHEN** `agent_write_enabled` 為 `False` 或 `True` 且 Agent 列出可用工具
- **THEN** 回應中 SHALL 只包含六個唯讀工具，不包含任何寫入類工具

#### Scenario: 寫入工具不得以設定開關提前曝光

- **WHEN** 操作者將 `agent_write_enabled` 設為 `True` 並重啟 MCP server
- **THEN** 寫入類工具 SHALL 仍不出現在工具列表中，直到 Phase 3 完成並啟用其獨立的完整 contract

#### Scenario: 本 change 不接受寫入呼叫

- **WHEN** Agent 以本 change 的 server 呼叫任一未列在 `tools/list` 的寫入 tool
- **THEN** server SHALL 回傳未知 tool 的 protocol error，且保持資料不變；不得以部分實作或開關值推測授權

