# admin-token-rotate-ui Specification

## Purpose

定義 `/setup/admin` 子頁與 backend `/api/setup/admin/token-*` 端點：使用者
透過 UI 取得 API token last-4 / created_at / version、執行 token rotate
並安全切換到新 token（atomic write 0600 / version bump / cookie 立即
失效）。落地於 oauth-onboarding-ui change（v0.1.0 GA）。

## Requirements

### Requirement: GET /api/setup/admin/token-info 顯示 last-4 與 created_at

系統 SHALL 提供 `GET /api/setup/admin/token-info` 端點，回傳目前 API token 的非敏感資訊：`{last4: str, created_at: datetime, version: int}`。`last4` SHALL 為 token 後四個字元；`created_at` SHALL 從 `${CCAS_DATA_LOCATION}/secrets/api-token` 檔案 mtime 取；`version` SHALL 從 `${CCAS_DATA_LOCATION}/secrets/api-token-version` 純整數檔讀取。

#### Scenario: 不洩漏完整 token

- **WHEN** 前端呼叫 `GET /api/setup/admin/token-info`、目前 token 為 `abc123...xyz789f0`（64 hex）
- **THEN** response SHALL 為 `{last4: "9f0", created_at: ..., version: 1}` 或類似（last4 為實際後四字元）；response body grep SHALL 不含 token 完整字串

#### Scenario: 首次啟動 version 為 1

- **WHEN** 全新部署、entrypoint 自動產生 API token、`api-token-version` 不存在
- **THEN** entrypoint SHALL 同時建立 `api-token-version` 內容為 `1`；token-info 回 `version: 1`

#### Scenario: token 不存在時回錯

- **WHEN** `secrets/api-token` 檔案不存在（理論上不應發生，entrypoint 會自動產生）
- **THEN** 系統 SHALL 回 500 並錯誤訊息「API token 缺失，請檢查容器啟動」，不洩漏 secrets 目錄路徑

### Requirement: POST /api/setup/admin/token-rotate 旋轉 + 立即失效

系統 SHALL 提供 `POST /api/setup/admin/token-rotate` 端點，執行五步流程：(1) 產生新 32-byte hex、(2) 寫入 `${CCAS_DATA_LOCATION}/secrets/api-token`（覆寫權限 0600）、(3) 重置 backend in-memory `Settings.api_token` cache、(4) 增加 `secrets/api-token-version` 數值（int + 1）、(5) response 回新 token 明文一次。Rotate 完成後 SHALL 舊 token 與舊 cookie session 立即失效（401）。

#### Scenario: rotate 後舊 token 401

- **WHEN** 使用者 rotate、新 token 為 `new_xyz`、隨後第三方腳本用舊 token 呼叫 `/api/health`
- **THEN** 系統 SHALL 回 401（既有 verify_token 用 `Settings.api_token` 動態讀取）

#### Scenario: rotate 後舊 cookie session 401

- **WHEN** 使用者於 browser 已登入、有效 cookie session（payload 含 `token_version: 1`），rotate 後 `token-version` 變 2
- **THEN** 後端驗證 cookie session 時 SHALL 對比當前 `token-version`，不符 SHALL 回 401；前端瀏覽器 SHALL 被踢回 `/login`

#### Scenario: response 含完整新 token 一次

- **WHEN** rotate 成功
- **THEN** response body SHALL 為 `{token: "<new_64_hex>", version: 2, created_at: ...}`，含完整新 token 明文；前端 SHALL 立即顯示 + 複製到剪貼簿（預設動作）

#### Scenario: rotate 對 in-memory cache 即時生效

- **WHEN** rotate 完成、worker / scheduler 共用 data volume 讀同一 file
- **THEN** worker / scheduler 後續從 file 讀取 SHALL 取得新值（單元測試以 fake `Settings` reload 驗證）

### Requirement: token rotate 前端流程

系統 SHALL 提供 `frontend/src/pages/setup/admin.tsx`，路由 `/setup/admin`。頁面 SHALL 顯示 token last-4 + created_at + 「產生新 token」按鈕。點擊按鈕 SHALL 彈 confirm dialog 含明確警告「rotate 後舊 token / cookie 立即失效，請先驗證能用新 token 登入再關閉此頁」。Rotate 成功後新 token 顯示於 dialog 含「複製到剪貼簿」按鈕（預設已複製），關閉 dialog 後 frontend SHALL 自動清除 cookie session、redirect 至 `/login`。

#### Scenario: 確認對話框含警告

- **WHEN** 使用者點「產生新 token」按鈕
- **THEN** 系統 SHALL 彈 dialog 含警告文字、需使用者點「我了解，確認 rotate」才送 mutation；提供「取消」按鈕關閉對話框

#### Scenario: rotate 成功顯示 + 複製

- **WHEN** mutation 成功、收到 `{token, version, created_at}`
- **THEN** dialog SHALL 顯示完整新 token、自動複製到剪貼簿、顯示 toast「已複製」、提供「關閉並重新登入」按鈕

#### Scenario: 關閉後自動踢出

- **WHEN** 使用者點「關閉並重新登入」按鈕
- **THEN** frontend SHALL 呼叫 `/api/auth/logout`（清 cookie）、`window.location.href = '/login'`、login 頁面 SHALL 顯示提示「請用新 token 登入」

### Requirement: 既有 /settings 路由 redirect 到 /setup/admin

系統 SHALL 將既有 `/settings` 路由（compose-pull-deploy 之前的 API token 顯示頁）改為 redirect 至 `/setup/admin`，避免外部書籤失效，同時收斂「設定中心」入口。

#### Scenario: 舊書籤仍可用

- **WHEN** 使用者開啟舊書籤 `/settings`
- **THEN** frontend SHALL 立即 redirect 至 `/setup/admin`、無需手動找新路徑

#### Scenario: NAV 不再顯示舊 /settings

- **WHEN** 使用者瀏覽主 nav
- **THEN** NAV SHALL 顯示「設定中心」項（連到 `/setup/gmail` 預設子頁），不再有獨立「Settings」項

### Requirement: token rotate 後 audit log

系統 SHALL 在 token rotate 時 stdout log 記錄 `[INFO] API token rotated, version=N, by_session=<session_id_short>`，便於使用者事後追蹤。Log SHALL **不**含完整新 token 或舊 token；session_id_short SHALL 為當前操作 session 的前 8 字元（既有 cookie session 已有 id）。

#### Scenario: rotate 留下 audit trail

- **WHEN** 使用者點 rotate
- **THEN** backend stdout SHALL 出現 `[INFO] API token rotated, version=2, by_session=abc12345`、不含 token 明文；既有 RedactingFilter SHALL 確保 log 不會洩漏

#### Scenario: 無認證 session 時拒絕 rotate

- **WHEN** 攻擊者直接 POST `/api/setup/admin/token-rotate` 不帶 token
- **THEN** 既有 `verify_token` middleware SHALL 攔截、回 401、log 記錄 unauthorized rotate attempt（不執行 rotate）
