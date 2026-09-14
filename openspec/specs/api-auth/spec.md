# api-auth Specification

## Purpose
TBD - created by archiving change backend-api. Update Purpose after archive.
## Requirements
### Requirement: 所有業務 API 需通過 Bearer Token 認證

系統 SHALL 維持既有業務 API 的 `verify_token` 認證：接受有效 Bearer Token 或有效 session cookie；公開 health／auth 端點維持既有例外。本認證機制 SHALL 只涵蓋 HTTP 路徑（REST API／前端儀表板），不適用於 stdio MCP／CLI 路徑；stdio MCP／CLI 的本機可用性設定與 HTTP token 獨立（見下方新增 Requirement），兩者互不影響、互不取代。不得為本機 stdio 路徑額外移植 HTTP OAuth handshake。

#### Scenario: 帶有效 Token 的請求正常通過
- **WHEN** 請求的 `Authorization` header 帶有 `Bearer <valid_token>`
- **THEN** 請求正常轉發到對應的路由處理

#### Scenario: 缺少 Token 的請求被拒絕
- **WHEN** 請求未包含 `Authorization` header 且沒有有效 session cookie
- **THEN** API 回傳 `401 Unauthorized`

#### Scenario: Token 無效的請求被拒絕
- **WHEN** 請求的 `Authorization` header 帶有無效的 Token 且沒有有效 session cookie
- **THEN** API 回傳 `401 Unauthorized`

#### Scenario: `/health` 端點不需認證
- **WHEN** 請求呼叫 `GET /health`
- **THEN** 無論是否帶有 Token，都會正常回應

#### ADDED Scenario: stdio MCP／CLI 路徑不套用 Bearer Token 認證
- **WHEN** Agent 透過 stdio 連上 MCP server，或操作者執行 CLI
- **THEN** 系統 SHALL 不要求 `Authorization` header；本 change 只提供唯讀 MCP／CLI surface，`agent_write_enabled` 不得使尚未完成 contract 的寫入工具被註冊，實際寫入仍須另取得使用者明確授權

### Requirement: Agent 寫入工具設定保留為 Phase 3 本機信任閘門

系統 SHALL 提供設定項 `agent_write_enabled`（由環境變數 `AGENT_WRITE_ENABLED` 映射，預設 `False`），獨立於既有 Bearer Token 認證之外，作為 Phase 3 控制 stdio MCP／CLI 寫入類工具可用性的預留閘門。本 change 期間 MCP／CLI SHALL 只註冊／提供六個唯讀面，即使設定為 `True` 也不得曝光未完成 schema、錯誤、授權與副作用契約的寫入工具／子命令。此開關 SHALL 不影響、也不被既有 `verify_token` 邏輯影響；它只是工具可用性閘門，不取代每次寫入所需的使用者明確授權。

#### Scenario: 預設值為關閉
- **WHEN** 未設定 `AGENT_WRITE_ENABLED` 環境變數
- **THEN** 系統 SHALL 以 `False` 作為預設值，寫入工具不被註冊

#### Scenario: 開關變更不影響既有 HTTP 認證或本 change 的 read surface
- **WHEN** 操作者將 `agent_write_enabled` 設為 `True`
- **THEN** 既有 REST API 的 Bearer Token 認證行為 SHALL 不受任何影響，MCP／CLI 的工具清單仍只包含唯讀面，且開關本身不得被視為任何寫入操作的使用者授權

