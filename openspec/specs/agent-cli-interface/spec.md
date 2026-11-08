# agent-cli-interface Specification

## Purpose
TBD - created by archiving change add-agent-mcp-interface. Update Purpose after archive.
## Requirements
### Requirement: CLI 預設輸出 JSON

系統 SHALL 提供一個 CLI 進入點，讀取類子命令（對應 MCP 的六個唯讀工具）預設以 `--format json` 輸出；CLI JSON SHALL 是共用 Agent DTO payload，不得輸出 JSON-RPC request／response envelope。其 payload 欄位 SHALL 與對應 MCP tool 的 `structuredContent` 一致；金額 SHALL 沿用 `{ "currency": "TWD", "value": "<decimal-string>" }`。

#### Scenario: 查詢帳單列表

- **WHEN** 操作者執行 CLI 的帳單列表子命令且未指定 `--format`
- **THEN** 系統 SHALL 以 JSON 格式輸出到 stdout，payload 欄位與 `list_bills` MCP tool 的 `structuredContent` 一致，且不包含 JSON-RPC envelope

#### Scenario: 明確要求非 JSON 格式

- **WHEN** 操作者指定其他輸出格式（如純文字表格）
- **THEN** 系統 SHALL 支援該格式，但底層資料仍來自與 JSON 輸出相同的 service function 呼叫

### Requirement: CLI 與 MCP 共用同一組 service function

系統 SHALL 讓 CLI 子命令直接呼叫 `ccas/services/` 底下的函式，不得為 CLI 另外實作一份查詢邏輯。

#### Scenario: 契約一致性測試

- **WHEN** 執行 CLI 與 MCP 的契約一致性測試，對同一組查詢條件分別呼叫兩種介面
- **THEN** 兩者回傳的資料內容 SHALL 完全一致（欄位、數值、排序）

### Requirement: 本 change 不曝光未完成的寫入子命令

本 change 的 CLI SHALL 只提供六個唯讀查詢子命令，與 MCP 的六個工具一一對應；`agent_write_enabled` 在本 change 只保留為 Phase 3 預留設定，無論開關值為何都不得曝光尚未完成 schema、錯誤、授權與副作用契約的寫入子命令。Phase 3 若加入寫入命令，仍須逐次取得使用者明確授權。

#### Scenario: 嘗試執行未曝光的寫入子命令

- **WHEN** `agent_write_enabled` 為 `False` 或 `True` 且操作者執行本 change 未提供的寫入類子命令
- **THEN** CLI SHALL 以非零 exit code 與明確錯誤訊息拒絕執行，不得修改任何資料

### Requirement: CLI 回應內容永不包含 secrets

系統 SHALL 保證 CLI 任一子命令的輸出內容都不包含 PDF 密碼、OAuth refresh token、session secret 或完整信用卡卡號；卡號欄位只 SHALL 回傳既有的末四碼。此契約 SHALL 與 MCP 唯讀工具的 secrets 保護契約一致。

#### Scenario: CLI 查詢不外洩敏感資料

- **WHEN** 操作者執行任一讀取類 CLI 子命令
- **THEN** stdout 與 stderr SHALL 不包含上述 secrets 或完整卡號

### Requirement: CLI Agent datetime matches MCP canonical serialization

CLI 六個 read-only command 的 JSON output SHALL 使用與 MCP structuredContent 完全相同
的 Agent DTO serialization。所有 Agent datetime SHALL 是 UTC RFC3339 `Z` 字串；aware
value 轉為 UTC，SQLite 讀回的 naive value 視為 UTC，nullable datetime 保持 null。

#### Scenario: CLI and MCP serialize the same timestamps

- **WHEN** 對同一 SQLite fixture 分別執行 CLI 與 MCP 的對應 read query
- **THEN** 兩者 datetime 欄位 SHALL 完全一致，並都以 `Z` suffix 輸出

### Requirement: CLI 公開錯誤使用共用最小投影
CLI SHALL 使用與 MCP 相同的公開業務錯誤白名單：code、安全 message、必要時 needs_human=true。CLI SHALL NOT 輸出任意內部 data，包括 retries-exhausted 的完整 pipeline payload；失敗 SHALL 以非零退出碼及可解析 JSON 回報。

#### Scenario: 錯誤安全投影
- **WHEN** 查詢失敗或 retries exhausted，內部錯誤帶有敏感 message 與 data
- **THEN** CLI SHALL 非零退出，公開 JSON 不含敏感字串與內部 data，stdout／stderr 均安全

### Requirement: CLI 支援指定帳單月份預算評估
budget-status SHALL 接受 --month，使用 MCP 的共用月份驗證、預算查詢與 Agent DTO；JSON SHALL 與對應 MCP structuredContent 一致。指定月份 SHALL 使用目前預算設定及帳單月份歸屬，新增 assessment；未指定月份 SHALL 保持既有行為。--include-current-period SHALL 繼續只代表本月；table SHALL 明確呈現評估月份與目前設定基準。

#### Scenario: 指定歷史月份
- **WHEN** CLI 以 --month 查詢歷史帳單月份
- **THEN** JSON SHALL 與對應 MCP 一致，table SHALL 標示評估月份及使用目前預算設定

#### Scenario: 舊呼叫及無效月份
- **WHEN** 沒有 --month，或 month 格式無效
- **THEN** 前者 SHALL 保留舊行為；後者 SHALL 非零退出且回報安全 invalid_argument
