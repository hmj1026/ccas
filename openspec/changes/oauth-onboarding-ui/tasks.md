## 1. 加密與 master key 機制

- [ ] 1.1 新增 `backend/src/ccas/storage/secrets.py`：`MasterKeyManager` class（load_or_create、get_fernet、encrypt、decrypt 四個方法）；單元測試覆蓋 (a) 首次產生、(b) 既有讀取、(c) decrypt 錯誤訊息明確
- [ ] 1.2 修改 `scripts/docker-entrypoint.sh`：在 `API_TOKEN` bootstrap 段落之前新增 master.key 自動產生邏輯（`${CCAS_DATA_LOCATION}/secrets/master.key`，權限 0600，stdout INFO log）
- [ ] 1.3 為 entrypoint 段落寫 bats 單元測試：(a) 首次啟動產生 + 權限 0600、(b) 既有 master.key 不覆蓋
- [ ] 1.4 backend `Settings` 新增 `master_key_path` 與 lazy `master_key` property，從 file 讀取；測試覆蓋 file 不存在時的 error path
- [ ] 1.5 在 pyproject.toml `[project.optional-dependencies] api` 顯式宣告 `cryptography>=42` 版本下限

## 2. DB 模型與 migration

- [ ] 2.1 在 `backend/src/ccas/storage/models.py` 新增 `BankSettings` 模型（`code` PK, `enabled`, `display_name`, `notes`, `created_at`, `updated_at`）
- [ ] 2.2 新增 `BankSecret` 模型（`bank_code` PK, `encrypted_password`, `created_at`, `updated_at`）；註解明示 encrypted_password 為 base64 Fernet ciphertext
- [ ] 2.3 新增 `GmailOAuthState` 模型（`state` PK, `code_verifier`, `created_at`）
- [ ] 2.4 建立 alembic migration `<ts>_add_setup_tables.py`：建三張表，無外鍵到 banks.yaml；downgrade = drop tables
- [ ] 2.5 在乾淨 DB 跑 `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 驗證冪等
- [ ] 2.6 修改 entrypoint：在 alembic 之後新增 bank_settings seed 邏輯（讀 banks.yaml → INSERT OR IGNORE 預設 row）；單元測試覆蓋首次 seed、既有 row 不覆蓋

## 3. 後端 API：Gmail OAuth Web flow

- [ ] 3.1 建立 `backend/src/ccas/api/routers/setup/__init__.py` 與 `gmail.py`
- [ ] 3.2 實作 `POST /api/setup/gmail/credentials`：multipart upload，驗證 JSON 結構（含 `installed.client_id` 與 `installed.client_secret`）、寫入 `${CCAS_DATA_LOCATION}/gmail/credentials.json` 權限 0600
- [ ] 3.3 實作 `GET /api/setup/gmail/authorize`：產 PKCE code_verifier + state、寫入 `gmail_oauth_state` 表、回傳 Google authorize URL（含 `code_challenge`、`scope`、`redirect_uri`、`state`）
- [ ] 3.4 實作 `GET /api/setup/gmail/callback?code=&state=`：驗證 state 存在 + 未過期（10 分鐘），用 code + code_verifier 換 token、寫 `${CCAS_DATA_LOCATION}/gmail/token.json`、刪除 state row、redirect 回 `/setup/gmail?status=connected`
- [ ] 3.5 實作 `GET /api/setup/gmail/status`：回 `{connected: bool, email?: str, granted_scopes?: list}`，從 token.json 解析（若存在）
- [ ] 3.6 實作 `POST /api/setup/gmail/revoke`：刪除 token.json、撤銷 Google 端 token（呼叫 Google revoke endpoint）、回 200
- [ ] 3.7 新增 `Settings.public_base_url` env（預設 `http://localhost:${CCAS_PORT:-8080}`），用於組成 redirect_uri；docs 註明若使用者透過外部 reverse proxy 暴露需更新
- [ ] 3.8 entrypoint 啟動時 `DELETE FROM gmail_oauth_state WHERE created_at < NOW() - 1 day`（清理過期 state）
- [ ] 3.9 為四個端點寫 pytest 整合測試：覆蓋 happy path、state 過期、redirect_uri_mismatch（Google 端模擬 400）、credentials.json 缺失

## 4. 後端 API：bank-management

- [ ] 4.1 建立 `backend/src/ccas/api/routers/setup/banks.py`
- [ ] 4.2 實作 `GET /api/setup/banks`：JOIN banks.yaml metadata + bank_settings DB，回 `[{code, display_name, enabled, last_ingest_at, total_pdfs, ...}]`
- [ ] 4.3 實作 `PUT /api/setup/banks/{code}`：body `{enabled: bool, display_name?, notes?}`，UPDATE bank_settings；不存在 code 回 404
- [ ] 4.4 修改 `backend/src/ccas/ingestor/job.py`：bank enabled 檢查改為「`bank_settings.enabled`（DB）→ banks.yaml.enabled → 預設 true」優先序
- [ ] 4.5 修改 `parser/job.py` 與 `classifier/job.py`：同樣優先序
- [ ] 4.6 寫 pytest：DB enabled=false 時 ingest skip；DB 無 row + yaml.enabled=false 時 ingest skip；DB 無 row + yaml 無 enabled 欄位時預設 enabled
- [ ] 4.7 為 `GET /banks` 與 `PUT /banks/{code}` 寫 router 整合測試

## 5. 後端 API：pdf-secrets

- [ ] 5.1 建立 `backend/src/ccas/api/routers/setup/secrets.py`
- [ ] 5.2 實作 `GET /api/setup/secrets`：回 `[{bank_code, has_db_secret: bool, has_env_secret: bool, effective_source: "db"|"env"|"none"}]`，**不回密碼明文**
- [ ] 5.3 實作 `PUT /api/setup/secrets/{code}`：body `{password: str}`，用 master.key Fernet 加密、UPSERT bank_secrets
- [ ] 5.4 實作 `DELETE /api/setup/secrets/{code}`：刪除 bank_secrets row（env fallback 仍生效）
- [ ] 5.5 實作 `POST /api/setup/secrets/import-from-env`：掃描 `Settings.bank_passwords`（既有 env 解析）、對每個 env-only 條目 UPSERT bank_secrets、回 `{imported: N, skipped_already_in_db: M}`
- [ ] 5.6 修改 `backend/src/ccas/decryptor/passwords.py`：密碼解析優先序改為 `bank_secrets`（DB Fernet decrypt）→ env → 無；密碼錯誤訊息明確區分「DB 解密失敗（master.key 不匹配）」與「密碼錯誤」
- [ ] 5.7 寫 pytest：(a) DB 有 secret 優先 env、(b) 無 DB row 用 env、(c) DB 解密失敗 raise specific exception、(d) import-from-env 冪等
- [ ] 5.8 為四個端點寫 router 整合測試；驗證 `GET /secrets` 回應**不含**密碼明文（grep response body 應無實際密碼字串）

## 6. 後端 API：admin token rotate

- [ ] 6.1 建立 `backend/src/ccas/api/routers/setup/admin.py`
- [ ] 6.2 實作 `GET /api/setup/admin/token-info`：回 `{last4: str, created_at: datetime}`，從 `secrets/api-token` 與 file mtime 取
- [ ] 6.3 實作 `POST /api/setup/admin/token-rotate`：(a) 產新 hex、(b) 寫 `secrets/api-token`、(c) 重置 `Settings.api_token` cache、(d) 增加 `secrets/api-token-version` 數值、(e) response 回新 token 明文一次
- [ ] 6.4 修改 `backend/src/ccas/api/deps.py:verify_token`：從 `Settings.api_token` 動態讀取（不快取進 closure）
- [ ] 6.5 修改 cookie session 驗證邏輯：session payload 加入 `token_version`，每次驗證時對比當前 `secrets/api-token-version`，不符 SHALL 拒絕（401）
- [ ] 6.6 寫 pytest：(a) rotate 後舊 token 401、(b) rotate 後舊 cookie 401、(c) rotate response 含完整新 token、(d) token-info 不洩漏完整 token

## 7. 前端 layout 與路由

- [ ] 7.1 建立 `frontend/src/pages/setup/layout.tsx`：左側導覽含 4 子頁、頂部「設定中心」標題
- [ ] 7.2 修改 `frontend/src/components/layout.tsx` NAV_ITEMS：新增「設定中心」項，icon `Settings2`，連到 `/setup/gmail`
- [ ] 7.3 修改 `frontend/src/App.tsx`：lazy route 群組 `/setup/*`，子路由 `gmail/banks/secrets/admin`
- [ ] 7.4 舊 `/settings` route 改為 redirect 至 `/setup/admin`（avoid 書籤失效）
- [ ] 7.5 為 layout 寫 Vitest snapshot 測試

## 8. 前端：Gmail OAuth 頁

- [ ] 8.1 建立 `frontend/src/pages/setup/gmail.tsx`：階段式 UI（step 1 上傳 credentials.json、step 2 顯示 redirect URI 提示、step 3 「授權 Google」按鈕、step 4 連線狀態 + 「revoke」按鈕）
- [ ] 8.2 file input 上傳 credentials.json：使用 `useMutation` 對 `POST /api/setup/gmail/credentials`、成功後跳到 step 2
- [ ] 8.3 「授權 Google」按鈕：呼叫 `GET /api/setup/gmail/authorize` 取得 URL → `window.location.href = url` 跳轉 Google
- [ ] 8.4 callback 頁（route `/setup/gmail/callback`）：讀 query params、轉發到後端 `GET /api/setup/gmail/callback?code=...&state=...`、後端處理完 redirect 回 `/setup/gmail?status=connected`
- [ ] 8.5 連線狀態區塊：每 5 秒輪詢 `GET /api/setup/gmail/status`（直到 connected）；connected 後顯示 email + scopes
- [ ] 8.6 「revoke」按鈕：confirm dialog → `POST /api/setup/gmail/revoke`、成功後回 step 1
- [ ] 8.7 redirect URI 顯示區塊：明示「目前 redirect URI 為 `http://localhost:${CCAS_PORT}/setup/gmail/callback`，請確認 GCP Console 已加入此 URL」，含 docs 連結
- [ ] 8.8 為頁面寫 Vitest 測試（mock fetch）：上傳 → 授權 → 模擬 callback → 顯示 connected
- [ ] 8.9 撰寫 Playwright e2e `setup-gmail.spec.ts`：上傳 fixture credentials → 跳轉到模擬 OAuth 頁（mock Google）→ 驗證 callback 後狀態

## 9. 前端：bank-management 頁

- [ ] 9.1 建立 `frontend/src/pages/setup/banks.tsx`：表格（code / display_name / enabled toggle / 已收 PDF 數 / 最後 ingest 時間 / 操作按鈕）
- [ ] 9.2 enabled toggle 用 `<Switch>`（shadcn）：onChange 觸發 `useMutation` 對 `PUT /api/setup/banks/{code}`、樂觀更新
- [ ] 9.3 顯示「孤兒」標記：DB 有 row 但 banks.yaml 已無對應條目（`metadata_missing: true`），含「移除此 row」按鈕
- [ ] 9.4 列表頂部顯示「N 銀行已啟用 / M 已停用」摘要
- [ ] 9.5 寫 Vitest：toggle 觸發 PUT、樂觀更新、API 失敗時 revert
- [ ] 9.6 e2e：登入 → 進 `/setup/banks` → toggle 一個銀行 → 重整後狀態保留

## 10. 前端：pdf-secrets 頁

- [ ] 10.1 建立 `frontend/src/pages/setup/secrets.tsx`：表格（bank_code / 來源 badge / 「設定密碼」按鈕 / 「刪除 DB 條目」按鈕）
- [ ] 10.2 來源 badge 顏色：DB 綠、env 黃、none 灰；tooltip 顯示「DB 優先 env」邏輯
- [ ] 10.3 「設定密碼」對話框：input type=password、提交呼叫 `PUT /api/setup/secrets/{code}`
- [ ] 10.4 「刪除 DB 條目」對話框：確認後呼叫 `DELETE /api/setup/secrets/{code}`，明示「刪除後若 env 仍有則 fallback 生效，否則該銀行 PDF 解密將失敗」
- [ ] 10.5 「匯入 env 密碼」橫幅：頁面載入時若偵測 `has_env_secret` 且 `!has_db_secret` 條目存在 → 顯示「偵測到 N 個 env 密碼，是否一鍵匯入？」按鈕
- [ ] 10.6 master.key warning banner：頁面頂部顯示「master.key 是備份的關鍵，請定期備份 `${CCAS_DATA_LOCATION}` 目錄」（永久顯示，不可關閉）
- [ ] 10.7 寫 Vitest：來源 badge 渲染、設定 / 刪除 mutation、import-from-env 流程
- [ ] 10.8 e2e：設定一個密碼 → 重整後 source=db → 刪除 → source 變 env 或 none

## 11. 前端：admin token rotate 頁

- [ ] 11.1 建立 `frontend/src/pages/setup/admin.tsx`：顯示 token last-4 + created_at + 「產生新 token」按鈕
- [ ] 11.2 「產生新 token」對話框：警告「rotate 後舊 token / cookie 立即失效，請先確認新 token 可登入再關閉此頁」、確認後呼叫 `POST /api/setup/admin/token-rotate`
- [ ] 11.3 rotate 成功後 dialog 顯示新 token + 「複製到剪貼簿」按鈕（預設已複製）；關閉 dialog 後 frontend 立即清 cookie session、redirect 至 `/login`
- [ ] 11.4 寫 Vitest：rotate flow、cookie 清除、redirect
- [ ] 11.5 e2e：rotate 成功 → 驗證舊 cookie 無法用、新 token 能登入

## 12. Docs 更新

- [ ] 12.1 修改 `docs/install-quickstart.md`「目前仍需手動設定的項目」章節：改為「進入 `/setup/*` 完成設定」段落，提供四子頁連結；CLI / yaml fallback 段落收進「進階」附錄
- [ ] 12.2 修改 `docs/gmail-setup.md`：保留 GCP Console 步驟，於「取得 token.json」段落新增「Web flow 取代 CLI（推薦）」章節，連結 `/setup/gmail`；CLI 章節改為 fallback
- [ ] 12.3 撰寫 `docs/secrets-management.md`：master.key 機制、備份建議、env 與 DB 雙來源解析優先序、token rotate 流程
- [ ] 12.4 README 設定中心連結：簡介四子頁用途
- [ ] 12.5 在 `docs/upgrade-guide.md` 加入「升級到含 `/setup/*` 版本」段落：說明 master.key 自動產生、bank_settings seed、env fallback 仍生效

## 13. 端對端驗證

- [ ] 13.1 在乾淨 data 目錄啟動：驗證 entrypoint 自動產生 master.key 權限 0600、bank_settings seed 從 banks.yaml
- [ ] 13.2 Gmail Web flow 端對端：上傳 credentials.json → 授權 → callback → 看到 connected → revoke → 驗證 token.json 已刪
- [ ] 13.3 bank toggle 端對端：停用某銀行 → 跑 pipeline → 該銀行 attachments 被 skip
- [ ] 13.4 pdf-secrets 端對端：DB 設定密碼 → 跑 pipeline 解密成功；刪除 DB 條目 + env 仍存在 → 解密成功（fallback）；刪除 DB + 刪除 env → 解密失敗 + 明確錯誤訊息
- [ ] 13.5 import-from-env 端對端：env 設 5 個密碼、DB 空 → 進 `/setup/secrets` 看橫幅 → 點匯入 → DB 5 條 → env 仍存在但不再生效
- [ ] 13.6 token rotate 端對端：登入 → rotate → 看到新 token → frontend 自動踢出 → 用新 token 登入成功 → 用舊 token 401
- [ ] 13.7 master.key 遺失 fail-loud：手動刪 master.key → 重啟 backend → 自動產生新 master.key → 既有 bank_secrets 解密失敗 → 錯誤訊息明確指出「master.key 不匹配」
- [ ] 13.8 redirect_uri 變更：將 `CCAS_PORT` 從 8080 改 12283 → 進 `/setup/gmail` 看到提示新 redirect URI → GCP Console 同步後可完成授權
- [ ] 13.9 升級相容性測試：既有 `.env` 含 `PDF_PASSWORD_*` + 既有 `banks.yaml.enabled=false` 某銀行 → 升級 → 跑 pipeline 行為不變
- [ ] 13.10 備份還原測試：tar 整個 `${CCAS_DATA_LOCATION}` → 在新機器解壓 + `up -d` → 所有 secrets / token / bank settings 完整復原

## 14. OpenSpec 收尾

- [ ] 14.1 `openspec validate oauth-onboarding-ui --strict` 通過
- [ ] 14.2 確認本 change 落地順序：須在 `compose-pull-deploy` 已合入後啟動實作（為 master.key 機制需要 entrypoint 結構）
- [ ] 14.3 完成後 `/opsx:archive oauth-onboarding-ui`，確認 delta 同步至 `openspec/specs/`
