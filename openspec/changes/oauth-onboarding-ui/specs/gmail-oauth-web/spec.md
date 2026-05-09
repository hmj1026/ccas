## ADDED Requirements

### Requirement: Gmail credentials.json Web 上傳取代 host file 操作

系統 SHALL 提供 `POST /api/setup/gmail/credentials` 端點接受 multipart 上傳 OAuth client `credentials.json`，後端 SHALL 驗證 JSON 結構（含 `installed.client_id` 與 `installed.client_secret`），寫入 `${CCAS_DATA_LOCATION}/gmail/credentials.json` 權限 0600。

#### Scenario: 使用者上傳合法 credentials.json

- **WHEN** 使用者於 `/setup/gmail` 上傳從 GCP Console 下載的 `credentials.json`
- **THEN** 系統 SHALL 驗證 JSON 包含 `installed.client_id` 與 `installed.client_secret`、寫入 data 目錄、回 200 並更新前端狀態為「credentials 已上傳」

#### Scenario: 上傳格式錯誤的檔案

- **WHEN** 使用者上傳非 OAuth client JSON 格式的檔案（如缺少 `installed` 欄位）
- **THEN** 系統 SHALL 回 400 並回應明確錯誤訊息（如「credentials.json 缺少 `installed.client_id` 欄位」），不寫入檔案

#### Scenario: 既有 credentials.json 被覆寫

- **WHEN** data 目錄已存在 `credentials.json` 且使用者重新上傳
- **THEN** 系統 SHALL 覆寫舊檔、保持權限 0600、stdout log 記錄 `[INFO] credentials.json 已被使用者重新上傳`

### Requirement: PKCE Authorization Code OAuth Web flow

系統 SHALL 提供 `GET /api/setup/gmail/authorize` 與 `GET /api/setup/gmail/callback` 兩個端點，實作標準 OAuth 2.0 PKCE Authorization Code flow，取代既有 host CLI 取得 `token.json` 的流程。`authorize` SHALL 產生 `code_verifier`（128-byte URL-safe random）與 `state`（32-byte URL-safe random）寫入 `gmail_oauth_state` 表、回傳 Google authorize URL。`callback` SHALL 驗證 state 存在且未過期（10 分鐘 TTL）、用 authorization code + code_verifier 換 token、寫入 `${CCAS_DATA_LOCATION}/gmail/token.json` 權限 0600、刪除 state row、redirect 至 `/setup/gmail?status=connected`。

#### Scenario: 使用者點「授權 Google」

- **WHEN** 使用者於 `/setup/gmail` 點擊「授權 Google」按鈕
- **THEN** 前端 SHALL 呼叫 `GET /api/setup/gmail/authorize`、收到 Google authorize URL（含 `code_challenge`、`scope=gmail.readonly`、`redirect_uri`、`state`、`code_challenge_method=S256`）、`window.location.href = url` 跳轉到 Google consent 頁

#### Scenario: Google 端授權成功

- **WHEN** 使用者於 Google consent 頁同意授權，Google redirect 回 `${PUBLIC_BASE_URL}/setup/gmail/callback?code=AUTH_CODE&state=STATE`
- **THEN** 後端 SHALL 驗證 state 存在於 `gmail_oauth_state` 且 `created_at` 在 10 分鐘內、用 code + code_verifier 呼叫 Google token endpoint 換 access + refresh token、寫入 `${CCAS_DATA_LOCATION}/gmail/token.json`、刪除 state row、redirect 至 `/setup/gmail?status=connected`

#### Scenario: state 過期或不存在

- **WHEN** callback 收到 state 在 DB 不存在或 `created_at` 超過 10 分鐘
- **THEN** 系統 SHALL 拒絕請求、回 400 並 redirect 至 `/setup/gmail?error=state_expired`、前端顯示「授權流程逾時，請重新點擊授權 Google」

#### Scenario: redirect_uri_mismatch 時錯誤訊息明確

- **WHEN** 使用者 GCP Console 未加入當前 `${PUBLIC_BASE_URL}/setup/gmail/callback`、Google 拒絕授權回 `error=redirect_uri_mismatch`
- **THEN** callback SHALL 偵測此錯誤、redirect 至 `/setup/gmail?error=redirect_uri_mismatch`、前端 SHALL 顯示「請至 GCP Console 加入 redirect URI: `<actual_uri>`」並含複製按鈕

#### Scenario: PKCE code_verifier 隨用隨棄

- **WHEN** callback 處理完成（成功或失敗）
- **THEN** 系統 SHALL 立即刪除對應的 `gmail_oauth_state` row，不得留存可被重放的 code_verifier

### Requirement: Gmail 連線狀態查詢與 revoke

系統 SHALL 提供 `GET /api/setup/gmail/status` 回 `{connected: bool, email?: str, granted_scopes?: list[str]}`，與 `POST /api/setup/gmail/revoke` 撤銷 token。`status` SHALL 從 `${CCAS_DATA_LOCATION}/gmail/token.json` 與 Google `tokeninfo` API 推導；`revoke` SHALL 呼叫 Google revoke endpoint、刪除 token.json。

#### Scenario: 已授權狀態查詢

- **WHEN** 前端輪詢 `GET /api/setup/gmail/status` 且 token.json 存在
- **THEN** 系統 SHALL 回 `{connected: true, email: "user@gmail.com", granted_scopes: ["gmail.readonly", ...]}`，email 來自 token 的 `id_token` 解析或 Google userinfo API

#### Scenario: 未授權狀態查詢

- **WHEN** token.json 不存在
- **THEN** 系統 SHALL 回 `{connected: false}`，不額外 callout Google

#### Scenario: revoke 撤銷授權

- **WHEN** 使用者點「revoke」按鈕、前端呼叫 `POST /api/setup/gmail/revoke`
- **THEN** 系統 SHALL 呼叫 Google `https://oauth2.googleapis.com/revoke?token=<refresh_token>`、刪除 `${CCAS_DATA_LOCATION}/gmail/token.json`、回 200；後續 `GET /status` SHALL 回 `connected: false`

### Requirement: redirect URI 與 PUBLIC_BASE_URL 設定可見性

系統 SHALL 新增 env `PUBLIC_BASE_URL`（預設 `http://localhost:${CCAS_PORT:-8080}`），用於組成 OAuth redirect_uri。前端 `/setup/gmail` 頁面在「授權 Google」按鈕之前 SHALL 顯著顯示「目前 redirect URI 為 `<PUBLIC_BASE_URL>/setup/gmail/callback`，請確認 GCP Console 已加入此 URL」並提供複製按鈕，避免使用者撞 redirect_uri_mismatch。

#### Scenario: 使用者改 CCAS_PORT 後 UI 顯示更新

- **WHEN** 使用者改 `.env` 的 `CCAS_PORT=12283` 並重啟、進 `/setup/gmail`
- **THEN** 頁面 SHALL 顯示 `http://localhost:12283/setup/gmail/callback`，前端 SHALL 不需要 rebuild image

#### Scenario: 使用者透過外部 reverse proxy 暴露

- **WHEN** 使用者於 `.env` 設 `PUBLIC_BASE_URL=https://ccas.mydomain.com`
- **THEN** redirect_uri SHALL 解析為 `https://ccas.mydomain.com/setup/gmail/callback`、authorize URL 內 `redirect_uri` 參數同步更新；docs/secrets-management.md SHALL 含此 use case 範例

### Requirement: gmail_oauth_state 表與啟動清理

系統 SHALL 提供 `gmail_oauth_state` 資料表（`state` PK、`code_verifier` text、`created_at` datetime），TTL 10 分鐘由 callback 時程式邏輯計算（不依賴 DB cron）。entrypoint 啟動時 SHALL 執行 `DELETE FROM gmail_oauth_state WHERE created_at < NOW() - 1 day` 清理積累。

#### Scenario: 並發多個 OAuth 嘗試不互相干擾

- **WHEN** 使用者開兩個瀏覽器分頁同時點「授權 Google」
- **THEN** 兩個 state 各自獨立寫入 DB、callback 時各自驗證對應 state；先完成的 callback 不影響另一個 state

#### Scenario: entrypoint 啟動清理舊 state

- **WHEN** backend 重啟、entrypoint 執行清理 SQL
- **THEN** 系統 SHALL 刪除所有 `created_at` 超過 1 天的 state row，不影響近期 row（10 分鐘內仍 valid）

### Requirement: docs 引導 Web flow 取代 CLI

`docs/gmail-setup.md` SHALL 在「取得 token.json」段落新增「Web flow（推薦）」章節，明示「Web flow 取代 CLI 為主要路徑、CLI 仍保留作為 fallback」。Web flow 章節 SHALL 含 (a) GCP Console 加入 redirect URI 的具體步驟與截圖描述、(b) `/setup/gmail` 操作流程、(c) redirect_uri_mismatch 排錯指引。

#### Scenario: 文件提供 Web flow 完整步驟

- **WHEN** 使用者依 `docs/gmail-setup.md` Web flow 章節操作
- **THEN** 從 GCP Console 加入 redirect URI 到取得 connected 狀態，過程 SHALL 全程在瀏覽器內完成（除了 GCP Console 操作），不需要 SSH 進機器或執行 host CLI

#### Scenario: 文件保留 CLI fallback 章節

- **WHEN** 使用者偏好 CLI（或在無 GUI 環境部署）
- **THEN** 文件 SHALL 保留 `python -m ccas.tools.gmail_auth` CLI 章節作為 fallback，註明「Web flow 為推薦路徑、CLI 適用於 headless 環境」
