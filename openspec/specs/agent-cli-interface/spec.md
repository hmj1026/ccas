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

