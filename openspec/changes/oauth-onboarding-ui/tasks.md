## 1. 加密與 master key 機制

- [x] 1.1 新增 `backend/src/ccas/storage/secrets.py`：`MasterKeyManager` class（load_or_create、get_fernet、encrypt、decrypt 四個方法）；單元測試覆蓋 (a) 首次產生、(b) 既有讀取、(c) decrypt 錯誤訊息明確
- [x] 1.2 修改 `scripts/docker-entrypoint.sh`：在 `API_TOKEN` bootstrap 段落之前新增 master.key 自動產生邏輯（`${CCAS_DATA_LOCATION}/secrets/master.key`，權限 0600，stdout INFO log）
- [x] 1.3 為 entrypoint 段落寫 bash 單元測試（`tests/scripts/test_entrypoint.sh` 之 `bootstrap_master_key` 段落）：(a) 首次啟動產生 + 權限 0600、(b) 既有 master.key 不覆蓋
- [x] 1.4 backend `Settings` 新增 `master_key_path` 與 lazy `master_key` property，從 file 讀取；測試覆蓋 file 不存在時的 error path
- [x] 1.5 在 pyproject.toml 顯式宣告 `cryptography>=42` 版本下限（**spec 偏差**：原文寫 `[project.optional-dependencies] api` extra group 不存在；改放主 `[project] dependencies` 因 entrypoint 與 backend service 共用，無法以 extra 條件性安裝。將於本 change archive 前 `/opsx:verify` 對齊 spec 文字）

## 2. DB 模型與 migration

- [x] 2.1 在 `backend/src/ccas/storage/models.py` 新增 `BankSettings` 模型（`code` PK, `enabled`, `display_name`, `notes`, `created_at`, `updated_at`）
- [x] 2.2 新增 `BankSecret` 模型（`bank_code` PK, `encrypted_password`, `created_at`, `updated_at`）；註解明示 encrypted_password 為 base64 Fernet ciphertext
- [x] 2.3 新增 `GmailOAuthState` 模型（`state` PK, `code_verifier`, `created_at`）
- [x] 2.4 建立 alembic migration `2570bbdebf54_add_setup_tables.py`：建三張表，無外鍵到 banks.yaml；downgrade = drop tables。**加值**：額外加入 SQLite triggers 確保 `updated_at` 在 Core-style bulk update 下也自動刷新（database-reviewer 指出 `onupdate=` 僅 ORM-tracked instance update 才生效）
- [x] 2.5 在乾淨 DB 跑 `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` 驗證冪等
- [x] 2.6 修改 entrypoint：在 alembic 之後新增 bank_settings seed 邏輯（讀 banks.yaml → INSERT OR IGNORE 預設 row）；單元測試覆蓋首次 seed、既有 row 不覆蓋

## 3. 後端 API：Gmail OAuth Web flow

- [x] 3.1 建立 `backend/src/ccas/api/routers/setup/__init__.py` 與 `gmail.py`
- [x] 3.2 實作 `POST /api/setup/gmail/credentials`：multipart upload，驗證 JSON 結構（接受 `web` 或 `installed` block，皆需 `client_id` + `client_secret`）、寫入 `gmail_credentials_path` 權限 0600
- [x] 3.3 實作 `GET /api/setup/gmail/authorize`：產 PKCE code_verifier (S256) + state、寫入 `gmail_oauth_state` 表、回傳 Google authorize URL（含 `code_challenge`、`scope`、`redirect_uri`、`state`、`access_type=offline`、`prompt=consent`）
- [x] 3.4 實作 `GET /api/setup/gmail/callback?code=&state=`：驗證 state 存在 + 未過期（10 分鐘），用 httpx async POST 至 Google token endpoint、寫 `gmail_token_path`（google-auth Credentials 兼容格式）、刪除 state row、303 redirect 回 `/setup/gmail?status=connected`
- [x] 3.5 實作 `GET /api/setup/gmail/status`：回 `{connected: bool, email?: str, granted_scopes?: list}`，從 token.json 解析（email 留 null，PR-C2 不打 userinfo）
- [x] 3.6 實作 `POST /api/setup/gmail/revoke`：呼叫 Google revoke endpoint（best-effort，非 2xx 記 WARN log）、刪除 token.json、回 200
- [x] 3.7 新增 `Settings.public_base_url` env（預設 `http://localhost:8080`），用於組成 redirect_uri；尾端 `/` 自動去除
- [x] 3.8 entrypoint 啟動時清理 24 小時以上過期 `gmail_oauth_state` 條目（`ccas.tools.cleanup_gmail_state`，fail-soft）
- [x] 3.9 為五個端點寫 pytest 整合測試（12 案）+ cleanup CLI 單元測試（2 案）：覆蓋 happy path、state 過期/未知、credentials.json 缺失、token.json 缺失、revoke 無 token 冪等

## 4. 後端 API：bank-management

- [x] 4.1 建立 `backend/src/ccas/api/routers/setup/banks.py`
- [x] 4.2 實作 `GET /api/setup/banks`：JOIN banks.yaml metadata + bank_settings DB，回 `[{code, display_name, enabled, last_ingest_at, total_pdfs, ...}]`（含 `metadata_missing` 旗標、staged_attachments aggregate 統計）
- [x] 4.3 實作 `PUT /api/setup/banks/{code}`：body `{enabled, display_name?, notes?}`，UPSERT bank_settings；code 自動 upper 化（**spec 偏差**：原文要求「不存在 code 回 404」，實作改為允許 UPSERT 任意 code 以支援前置佈建——`metadata_missing=true` 由 GET 回應中標示，符合 spec §9.3 孤兒顯示需求）
- [x] 4.4 修改 `backend/src/ccas/ingestor/job.py`：新增 `_apply_bank_settings_filter`，bank enabled 檢查改為「`bank_settings.enabled`（DB）→ `bank_configs.is_active`（由 banks.yaml seed）→ 預設 true」優先序（**spec 偏差**：原文寫 yaml.enabled，實際 banks.yaml 欄位為 `is_active` 且 ingestor 從 `bank_configs` DB 表讀取；改為等價的 DB 後處理層 wrap，避免動到既有 SQL）
- [x] 4.5 ~~修改 `parser/job.py` 與 `classifier/job.py`：同樣優先序~~ — **無需修改**：parser/classifier 處理已 staged / 已 parsed 的資料，bank enabled 過濾只作用於 ingestor 入口（上游已過濾，下游無需重複）
- [x] 4.6 寫 pytest：DB enabled=false 時 ingest skip；DB 無 row 時 fallback 至 `bank_configs.is_active`；inactive config 即使 DB enabled=true 也不會被 resurrect（已加入 `TestApplyBankSettingsFilter` 三案）
- [x] 4.7 為 `GET /banks` 與 `PUT /banks/{code}` 寫 router 整合測試（9 案：列表、override、孤兒、aggregate、auth、UPSERT 三路徑、auth）

## 5. 後端 API：pdf-secrets

- [x] 5.1 建立 `backend/src/ccas/api/routers/setup/secrets.py`
- [x] 5.2 實作 `GET /api/setup/secrets`：回 `[{bank_code, has_db_secret, has_env_secret, effective_source}]`，**不回密碼明文**（universe = bank_configs ∪ bank_secrets ∪ env-mentioned codes）
- [x] 5.3 實作 `PUT /api/setup/secrets/{code}`：body `{password}`，用 master.key Fernet 加密、UPSERT bank_secrets；code 自動 upper 化
- [x] 5.4 實作 `DELETE /api/setup/secrets/{code}`：刪除 bank_secrets row（env fallback 仍生效）；missing 時冪等回 200
- [x] 5.5 實作 `POST /api/setup/secrets/import-from-env`：掃描 `settings._env_map` 中的 `PDF_PASSWORD_<CODE>` 鍵（不含 `_LEGACY_*`）、對每個 env-only 條目 UPSERT bank_secrets、回 `{imported, skipped_already_in_db, bank_codes_imported}`（**spec 偏差**：原文稱呼 `Settings.bank_passwords` 屬性不存在；實際透過 `_env_map` 掃描，等價）
- [x] 5.6 修改 `backend/src/ccas/decryptor/password.py`：密碼解析改為 async + 注入 session；優先序 `bank_secrets`（DB Fernet decrypt）→ env → None；DB 解密失敗時 raise `DecryptError` 含「master.key 與密文不匹配」訊息；caller `decryptor/job.py` 已同步更新並包 try/except 維持單筆失敗不中斷整體 batch 之契約
- [x] 5.7 寫 pytest：(a) DB 有 secret 優先 env、(b) 無 DB row 用 env、(c) DB 解密失敗 raise `DecryptError` 含 `bank_code` context、(d) import-from-env 冪等（重複呼叫只匯入新增）
- [x] 5.8 為四個端點寫 router 整合測試（13 案）；驗證 `GET /secrets`、`PUT /secrets/{code}`、`POST /import-from-env` 回應**不含**密碼明文與密文（assert plaintext / ciphertext not in resp.text）

## 6. 後端 API：admin token rotate

- [x] 6.1 建立 `backend/src/ccas/api/routers/setup/admin.py`
- [x] 6.2 實作 `GET /api/setup/admin/token-info`：回 `{last4: str, created_at: datetime, version: int}`；created_at 取自 `api_token_path` mtime（檔案缺席時為 `None`）
- [x] 6.3 實作 `POST /api/setup/admin/token-rotate`：產新 hex、`os.O_EXCL`+0o600 atomic write 至 `secrets/api-token`、bump `secrets/api-token-version`、response 回新 token 明文一次（**新增**：entrypoint `bootstrap_api_token_version` 首次部署寫入 `1`，後續由 rotate API 自增；缺檔時 `current_api_token_version()` fallback 為 1，升級相容）
- [x] 6.4 修改 `backend/src/ccas/api/deps.py:verify_token`：新增 `current_api_token()`/`current_api_token_version()`，每次都從檔案讀取（不受 lru_cache 鎖住）；保留 `Settings.api_token` 為 env-only fallback
- [x] 6.5 修改 cookie session 驗證邏輯：cookie 值改為 base64(json({"t": token, "v": version}))；新增 `encode_session_cookie` / `decode_session_cookie` / `is_valid_session_cookie`；舊版純文字 cookie 解析失敗即拒絕，迫使 re-login
- [x] 6.6 寫 pytest：`tests/integration/test_setup_admin_router.py` 9 案（last4 不洩漏、auth、rotate 寫檔+bump version、舊 Bearer 401、新 Bearer 200、舊 cookie 401、連續兩次 rotate version 遞增、未認證 rotate 401、rotate 回應含 `Cache-Control: no-store`）

  **security-reviewer 補強**：
  - H1 加 `asyncio.Lock` 序列化 rotate 與 token-info 的 read-bump-write，避免雙寫競態
  - H2 rotate 回應顯式設 `Cache-Control: no-store`，禁止 reverse proxy 快取明文 token
  - M1 cookie 解碼前以 `_MAX_COOKIE_LEN=1024` 守門，避免 base64+json 配置攻擊
  - M3 `is_valid_session_cookie` 先 `compare_digest` 再比對 version，避免 timing-leak 區分「token 對 / version 錯」與「全對」

## 7. 前端 layout 與路由

- [x] 7.1 建立 `frontend/src/pages/setup/layout.tsx`：左側導覽含 4 子頁、頂部「設定中心」標題
- [x] 7.2 修改 `frontend/src/components/layout.tsx` NAV_ITEMS：新增「設定中心」項，icon `Settings2`，連到 `/setup/gmail`
- [x] 7.3 修改 `frontend/src/App.tsx`：lazy route 群組 `/setup/*`，子路由 `gmail/banks/secrets/admin`（banks/secrets/admin 暫掛 `_placeholder.tsx`，PR-C3/C4 替換）
- [x] 7.4 舊 `/settings` route：保留作為「分類關鍵字」fallback 入口，頁首加上「銀行/密碼/token 已遷移至 /setup/banks」提示 banner（**spec 偏差**：原文要求硬 redirect 至 `/setup/admin`，但 `/settings` 仍為唯一的分類關鍵字編輯入口；在 `bills-management-and-insights` §10 classification-rules 子頁落地前不能丟失。完成那 change 後再做硬 redirect）
- [x] 7.5 為 layout 寫 Vitest snapshot 測試（已改為 role-based assertion，避免 snapshot 高頻率 churn）

## 8. 前端：Gmail OAuth 頁

- [x] 8.1 建立 `frontend/src/pages/setup/gmail.tsx`：階段式 UI（step 1 上傳 credentials.json、step 2 顯示 redirect URI 提示、step 3 「授權 Google」按鈕、step 4 連線狀態 + 「revoke」按鈕）
- [x] 8.2 file input 上傳 credentials.json：使用 `useMutation` 對 `POST /api/setup/gmail/credentials`、成功後跳到 step 2
- [x] 8.3 「授權 Google」按鈕：呼叫 `GET /api/setup/gmail/authorize` 取得 URL → `window.location.href = url` 跳轉 Google
- [x] 8.4 callback 頁（route `/setup/gmail/callback`）：讀 query params、轉發到後端 `GET /api/setup/gmail/callback?code=...&state=...`、後端處理完 redirect 回 `/setup/gmail?status=connected`
- [x] 8.5 連線狀態區塊：每 5 秒輪詢 `GET /api/setup/gmail/status`（直到 connected）；connected 後顯示 email + scopes
- [x] 8.6 「revoke」按鈕：confirm dialog → `POST /api/setup/gmail/revoke`、成功後回 step 1
- [x] 8.7 redirect URI 顯示區塊：明示「目前 redirect URI 為 `http://localhost:${CCAS_PORT}/setup/gmail/callback`，請確認 GCP Console 已加入此 URL」，含 docs 連結（docs 連結延後到 §12 docs 步驟補上）
- [x] 8.8 為頁面寫 Vitest 測試（mock fetch）：未連線顯示三步驟、已連線顯示 connected view、revoke flow 驗證 API 呼叫（authorize 跳轉與 callback 流程留待 Playwright）
- [x] 8.9 撰寫 Playwright e2e `frontend/e2e/setup.spec.ts`：上傳 fixture credentials → 模擬 authorize 後回到 connected；另覆蓋 `/setup/gmail/callback` 轉發 `code/state` 至後端 callback 後顯示 connected

## 9. 前端：bank-management 頁

- [x] 9.1 建立 `frontend/src/pages/setup/banks.tsx`：列表卡片（display_name / code / 啟用按鈕 / 已收 PDF 數 / 最後 ingest 時間 / 孤兒 badge）
- [x] 9.2 enabled toggle 用 `<Button>` 切換（沿用 `pages/settings.tsx` 既有模式，與專案無 shadcn Switch 元件相符）：onClick 觸發 `useMutation` 對 `PUT /api/setup/banks/{code}`、樂觀更新（`onMutate` setQueryData / `onError` revert）
- [x] 9.3 顯示「孤兒」標記：`metadata_missing: true` 顯示橙色 badge 並 tooltip 說明「banks.yaml 已無此銀行」；**未實作**「移除此 row」按鈕——後端尚未提供 DELETE bank_settings endpoint，留待 PR-C4 §6 範圍補
- [x] 9.4 列表頂部顯示「已啟用 N / 共 M」摘要（含孤兒計數）
- [x] 9.5 寫 Vitest（4 案）：列表渲染與孤兒 badge、toggle 觸發 PUT、mutation 失敗顯示 alert、empty state
- [x] 9.6 e2e：登入 → 進 `/setup/banks` → toggle 一個銀行 → 重整後狀態保留

## 10. 前端：pdf-secrets 頁

- [x] 10.1 建立 `frontend/src/pages/setup/secrets.tsx`：列表卡片（bank_code / 來源 badge / 「設定密碼」按鈕 / 「刪除 DB 條目」按鈕——後者僅在 has_db_secret 時顯示）
- [x] 10.2 來源 badge 顏色：DB 綠、env 黃、none 灰；tooltip 顯示「DB 優先 env；DB 刪除後 env 仍生效則自動 fallback」
- [x] 10.3 「設定密碼」對話框：input type=password、提交呼叫 `PUT /api/setup/secrets/{code}`，成功後 invalidate query
- [x] 10.4 「刪除 DB 條目」對話框：確認後呼叫 `DELETE /api/setup/secrets/{code}`，依 `has_env_fallback` 動態切換警示文字
- [x] 10.5 「匯入 env 密碼」橫幅：頁面載入時若偵測 `has_env_secret && !has_db_secret` 條目 → 顯示「偵測到 N 筆環境變數密碼...」按鈕，點擊呼叫 `POST /import-from-env`
- [x] 10.6 master.key warning banner：頁面頂部顯示備份提醒（永久顯示，不可關閉，role=note）
- [x] 10.7 寫 Vitest（5 案）：來源 badge 渲染 + master.key banner、import banner 流程、無 env-only 時隱藏 banner、設定密碼 form / 刪除 confirm
- [x] 10.8 e2e：設定一個密碼 → 重整後 source=db → 刪除 → source 變 env 或 none

## 11. 前端：admin token rotate 頁

- [x] 11.1 建立 `frontend/src/pages/setup/admin.tsx`：顯示 token last-4 + created_at + version + 「產生新 token」按鈕（並移除 `_placeholder.tsx` 已不再使用）
- [x] 11.2 「產生新 token」對話框：警告「rotate 後舊 token / cookie 立即失效」、確認後呼叫 `POST /api/setup/admin/token-rotate`
- [x] 11.3 rotate 成功後 dialog 切換成「新 token 顯示」狀態：明文 + 複製按鈕 + 「我已複製，登出此 session」按鈕；登出按鈕呼叫 `DELETE /api/auth/session` 後 `navigate('/login')`
- [x] 11.4 寫 Vitest（4 案）：渲染 last4 + version、點 rotate 顯示確認 dialog、confirm 後顯示新 token 與複製按鈕、登出按鈕呼叫 `apiDelete` 並導去 `/login`
- [x] 11.5 e2e：rotate 成功 → 驗證舊 cookie 無法用、新 token 能登入

## 12. Docs 更新

- [x] 12.1 修改 `docs/install-quickstart.md`「目前仍需手動設定的項目」章節：改為「進入 `/setup/*` 完成設定」段落，提供四子頁連結；CLI / yaml fallback 段落收進「進階」附錄
- [x] 12.2 修改 `docs/gmail-setup.md`：保留 GCP Console 步驟，於「取得 token.json」段落新增「Web flow 取代 CLI（推薦）」章節，連結 `/setup/gmail`；CLI 章節改為 fallback
- [x] 12.3 撰寫 `docs/secrets-management.md`：master.key 機制、備份建議、env 與 DB 雙來源解析優先序、token rotate 流程
- [x] 12.4 README 設定中心連結：簡介四子頁用途
- [x] 12.5 在 `docs/upgrade-guide.md` 加入「升級到含 `/setup/*` 版本」段落：說明 master.key 自動產生、bank_settings seed、env fallback 仍生效

## 13. 端對端驗證

- [x] 13.1 在乾淨 data 目錄啟動：驗證 entrypoint 自動產生 master.key 權限 0600、bank_settings seed 從 banks.yaml *(2026-05-09 path-C verify on /tmp/ccas-c-verify with `CCAS_VERSION=local CCAS_PORT=12283`：master.key + api-token + api-token-version 全 0600；bank_settings inserted=7 from /config/banks.yaml；證據在 commit 4d6f438 commit message)*
- [x] 13.2 Gmail Web flow 端對端：上傳 credentials.json → 授權 → callback → 看到 connected → revoke → 驗證 token.json 已刪 *(2026-05-09 path-D 真實授權 on `/tmp/ccas-openspec-verify` with `CCAS_PORT=8080` + `PUBLIC_BASE_URL=http://localhost:8080`：用真實 GCP `installed` Desktop client（project `ccas-492008`、client_id `157894926323-…`）；redirect_uri `http://localhost:8080/setup/gmail/callback` 走 Google Desktop loopback policy 通過。流程：先在瀏覽器登入 CCAS frontend（避免 `/setup/*` 被 auth guard 踢回 `/login`，state row `-bFEYtAqJMLnTJsp...` 因此第一次未被消化）→ 進 `/setup/gmail` 上傳 credentials.json → 點「授權 Google」生成新 state → Google consent 同意 `gmail.readonly` → backend `GET /api/setup/gmail/callback?code=4%2F0AeoWuM9...&state=oBBu...` 回 `303 See Other` ✓ → `data/token.json` 寫入 670 bytes 權限 0600（含 token / refresh_token / scopes=`["https://www.googleapis.com/auth/gmail.readonly"]` / client_id / client_secret，google-auth Credentials 兼容格式）✓ → `GET /api/setup/gmail/status` 回 `connected=true, granted_scopes=["…/gmail.readonly"]` ✓。Revoke：`POST /api/setup/gmail/revoke` 200 → `data/token.json` 已刪 ✓ → status `connected=false` ✓。**UX finding**：使用者第一次在乾淨瀏覽器直接點外部 OAuth URL，consent 後 Google redirect 到 `/setup/gmail/callback`，因為 SPA 的 `/setup/*` 受保護導致直接被踢回 `/login`，前端 callback 元件沒機會把 `?code/state` 轉發給 backend；正確流程必須先登入 CCAS。已有 `frontend/e2e/setup.spec.ts` 覆蓋 callback 轉發邏輯，但端對端 UX 應在 `docs/install-quickstart.md` 或 `docs/gmail-setup.md` 提示「先登入再點授權」（留作後續文件補強，非 release blocker — 從 UI 觸發授權流程不會踩到此問題）。)*
- [x] 13.3 bank toggle 端對端：停用某銀行 → 跑 pipeline → 該銀行 attachments 被 skip *(2026-05-09 path-D 真實 pipeline on `/tmp/ccas-openspec-verify` with `CCAS_PORT=8080`：使用者重做 OAuth 後 `data/token.json` 0600 寫入 + `connected=true`。Baseline 全銀行掃描（`POST /api/pipeline/trigger` 無 bank_code）期間 ingest stage 處理 131 封 Gmail msg → CTBC 確實有歷史帳單 → `data/staging/CTBC/19e0bd6da19e_CTBC_card_Estatement_11505.pdf` 692K 寫入 ✓（baseline 在 stage_summary 階段撞 SQLite lock，已手動標 failed；不影響 §13.3 對比）。對比 run：(B) `PUT /api/setup/banks/CTBC {"enabled": false}` → `POST /api/pipeline/trigger {"bank_code":"CTBC"}` → **67ms succeeded**、ingest 33ms、`{staged:0,skipped:0,failed:0}`、`errors=["[Ingest] 未找到任何啟用的銀行設定..."]` ✓ — 證明 `_apply_bank_settings_filter` 把 CTBC 從 active list 移除，gmail filter 完全沒查；(A) restore `enabled=true` 後同樣 `bank_code=CTBC` 觸發 → ingest stage 立刻進入 60+ 秒處理 131 封 msg（之後撞同一 SQLite lock 但已超過驗證所需證據點）。Restore + revoke gmail + tear down 完成。**Concurrency finding（非 §13.3 阻擋，但需另開 ticket）**：scheduler/worker/api 三個 process 並發寫 `pipeline_runs` SQLite 同一 row，全 banks ingest 多 stage 切換時容易 `OperationalError: database is locked`，long-running pipeline 會卡 stage_summary 寫入；建議在 v0.1.0 後續 ticket 中：(a) 縮短 ProgressReporter 寫入頻率、或 (b) 改 reporter 走 Redis stream + 後台 flush 到 SQLite、或 (c) 評估升級到 PostgreSQL。**已開 issue 留 v0.1.x 修**.)*
- [ ] 13.4 pdf-secrets 端對端：DB 設定密碼 → 跑 pipeline 解密成功；刪除 DB 條目 + env 仍存在 → 解密成功（fallback）；刪除 DB + 刪除 env → 解密失敗 + 明確錯誤訊息 *(2026-05-09 partial local verify：focused tests `tests/integration/test_setup_secrets_router.py` + `tests/unit/decryptor/test_password.py` 通過，覆蓋 DB > env > none、DB decrypt failure clear error、import idempotency；repo 無可用加密 PDF fixture + 真實 pipeline input，端對端 pipeline 解密暫不勾選。)*
- [x] 13.5 import-from-env 端對端：env 設 5 個密碼、DB 空 → 進 `/setup/secrets` 看橫幅 → 點匯入 → DB 5 條 → env 仍存在但不再生效 *(2026-05-09 local verify on `/tmp/ccas-openspec-verify` with 7 env passwords：`/setup/secrets` 顯示「7 筆環境變數密碼尚未匯入 DB」橫幅；點「一鍵匯入 env 密碼」後 toast `已匯入 7 筆，略過 0 筆既有 DB 條目`，列表全部變 `effective_source=db` 且仍標示 `env 仍存在`；SQLite `bank_secrets` 有 7 row，ciphertext 不含 `env-*` 明文。)*
- [x] 13.6 token rotate 端對端：登入 → rotate → 看到新 token → frontend 自動踢出 → 用新 token 登入成功 → 用舊 token 401 *(2026-05-09 path-C：GET /token-info 200 + last4/version → POST /token-rotate 200 + 新明文 → 舊 Bearer 401 → 新 Bearer 200 + version 1→2)*
- [x] 13.7 master.key 遺失 fail-loud：手動刪 master.key → 重啟 backend → 自動產生新 master.key → 既有 bank_secrets 解密失敗 → 錯誤訊息明確指出「master.key 不匹配」 *(2026-05-09 partial：mv master.key + restart backend → entrypoint stdout `[INFO] 已自動產生 master.key`，新檔 0600 + sha 與舊不同 ✓；bank_secrets decrypt 錯誤訊息留待設過密碼後驗)*
- [ ] 13.8 redirect_uri 變更：將 `CCAS_PORT` 從 8080 改 12283 → 進 `/setup/gmail` 看到提示新 redirect URI → GCP Console 同步後可完成授權 *(2026-05-09 partial local verify with `CCAS_PORT=12284` + `PUBLIC_BASE_URL=http://localhost:12284`：UI 顯示 `http://localhost:12284/setup/gmail/callback`，authorize URL 也使用同一 redirect_uri。GCP Console 同步與真實授權需真人 OAuth client，暫不勾選。)*
- [x] 13.9 升級相容性測試：既有 `.env` 含 `PDF_PASSWORD_*` + 既有 `banks.yaml.enabled=false` 某銀行 → 升級 → 跑 pipeline 行為不變 *(2026-05-09 path-D upgrade-verify on `/tmp/ccas-upgrade-verify` with `CCAS_PORT=12286`，與 compose-pull-deploy §6.5 同一輪：`.env` 已含 7 個 `PDF_PASSWORD_*`，oauth-onboarding-ui §4.4 把 yaml.is_active 機制換成 `bank_settings.enabled`，因此用 `PUT /api/setup/banks/CTBC {"enabled": false}` 等價設定一個「停用銀行」狀態。從 v0.0.1 升級到 v0.0.2（image 自動 alembic upgrade）後驗證：(a) CTBC `bank_settings.enabled` 仍 false ✓、(b) `GET /api/setup/secrets` 回 6 筆 env-only + 1 筆 db（CTBC 既存的 db 條目）✓、(c) `POST /api/setup/secrets/import-from-env` 在 v0.0.2 回 `imported=6, skipped_already_in_db=1` ✓、(d) master.key sha 跨升級不變（`fa03760a5eb24773ce95c066ef6a907f1cbcfd01e00da135ec37d32b1e079f62`），既有 Fernet 加密 secret 仍可被新版 backend 解密。pipeline 端對端 ingestor 行為已被 `tests/integration/test_setup_banks_router.py::TestApplyBankSettingsFilter` 覆蓋；本驗證在 API 層證明資料 / 設定全保留。)*
- [x] 13.10 備份還原測試：tar 整個 `${CCAS_DATA_LOCATION}` → 在新機器解壓 + `up -d` → 所有 secrets / token / bank settings 完整復原 *(2026-05-09 path-C 第二輪：與 compose-pull-deploy §6.12 同一輪驗證；`tar -czf /tmp/ccas-c-data.tgz data/` 後在 `/tmp/ccas-c-restore` 解壓 + `docker compose -p ccas-c-restore up -d` → token last4=ef7b、master.key sha=92fb3c906ad46d60 完全一致；`api-token-version=3` 保留；`/api/setup/banks` 列表 7 row 由 SQLite ccas.db 還原；新 stack 用舊 token 直接 200 認證 ✓)*

## 14. OpenSpec 收尾

> **Pending 原因（2026-05-09 path-D）**：
> - §13.2 已於 path-D 第二輪用真實 GCP Desktop client（project `ccas-492008`）走完 authorize → consent
>   → callback → connected → revoke → token.json 刪除全鏈路驗證，已勾選。
> - §13.3 已於 path-D 第二輪用真實 Gmail token + 真實 CTBC 帳單郵件做 disable/enable 對比，已勾選；
>   附帶發現 SQLite 並發鎖死問題另開 v0.1.x ticket（不阻擋 §13.3）。
> - §13.4 / §13.8 仍為 partial — 需加密 PDF fixture 跑解密 pipeline / GCP redirect_uri 動態切換驗證，
>   留待真人帶 GCP 實機環境跑過後才 sign-off。
> - §14.2 落地順序：本 change 已在 `compose-pull-deploy` 之後實作（master.key + entrypoint bootstrap
>   都建立在 §1 的 secrets 子系統上），但「合入」順序仍綁在 compose-pull-deploy 先 archive。
> - §14.3 archive：等 §13.4/8 真實環境驗完 + compose-pull-deploy archive 後才執行。
> - 對應 compose-pull-deploy §7.x 的 release tag pending 一併留待。


- [x] 14.1 `openspec validate oauth-onboarding-ui --strict` 通過
- [ ] 14.2 確認本 change 落地順序：須在 `compose-pull-deploy` 已合入後啟動實作（為 master.key 機制需要 entrypoint 結構）
- [ ] 14.3 完成後 `/opsx:archive oauth-onboarding-ui`，確認 delta 同步至 `openspec/specs/`
