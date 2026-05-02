## Why

`compose-pull-deploy` 完成後，使用者能用 `docker compose pull && up -d` 一鍵啟動服務、從 `secrets/api-token` 取 token 貼到 `/login` 進入 dashboard。但抵達 dashboard 後立刻會被四道**仍要回到 terminal / GCP Console / 文字編輯器**的牆擋住，無法只在瀏覽器內完成設定：

1. **Gmail OAuth credentials**：使用者必須去 Google Cloud Console 建立 OAuth Desktop client、下載 `credentials.json` 放到 data 目錄，再在 host 機器執行 `python -m ccas.tools.gmail_auth` 觸發 `localhost:0` callback 取得 `token.json`。Container 內無法完成（CLI 依賴 host loopback callback）。
2. **Bank 啟用清單**：要停用某銀行（如名下無玉山卡）需用編輯器改 `config/banks.yaml` 的 `enabled` 欄位，重啟 backend 才生效。
3. **PDF 解密密碼**：`PDF_PASSWORD_<BANK>` 散在 `.env`，使用者須查各銀行帳單 PDF 規則手填、明文存於 `.env`、新增銀行要 `docker compose down/up -d` 重啟。
4. **API token rotate / admin 概念**：目前 token 為 entrypoint 自動產生，使用者若想換新 token 必須砍 `secrets/api-token` 檔重啟 backend；無 admin user / role 概念，無法多人協作（即使單人本機自架也希望「在 UI 換 token」）。

`compose-pull-deploy/proposal.md:20` 已明文承諾本 change 處理這四件事，本 change 是該承諾的兌現。落地後使用者體驗將真正對齊 immich：**所有設定皆可在瀏覽器內完成，data 目錄即是備份單位**。

## What Changes

- 新增 `/setup` 前端區塊（lazy route，登入後可見），含四個子頁：
  - `/setup/gmail` — Gmail OAuth Web flow，瀏覽器點「授權 Google」後彈 OAuth consent → Google redirect 回 `/setup/gmail/callback` → 後端用 authorization code 換 `token.json` 並寫入 `${CCAS_DATA_LOCATION}/gmail/token.json`，使用者全程不需開 terminal。`credentials.json` 仍需使用者上傳（可用 file input），上傳後存於 data 目錄、明確顯示「下次更換需重新上傳」。
  - `/setup/banks` — bank 啟用清單表格（依 `bank_settings` 表），含 enable / disable toggle、顯示名稱、每銀行已收件 PDF 數、最後一次成功 parse 時間。停用某銀行後 ingest 階段 SHALL 跳過該銀行 attachments。
  - `/setup/secrets` — 各銀行 PDF 密碼編輯欄位（密碼遮罩顯示），存於 `bank_secrets` 表加密欄位（Fernet encrypted）；列表 SHALL 揭示哪些銀行已設定、哪些尚未。匯入歷史 `PDF_PASSWORD_*` env 為一鍵動作（首次進入頁面顯示「偵測到 N 個 env 密碼，是否匯入並從 env 移除？」橫幅）。
  - `/setup/admin` — token rotate UI：顯示目前 token last-4 chars、按鈕「產生新 token」會產生新 hex 寫入 `secrets/api-token`、舊 cookie session 立即失效、使用者需用新 token 重新登入。
- 後端新增 `/api/setup/*` routers：
  - `gmail.py` — `POST /credentials`（上傳檔案）、`GET /authorize`（取 Google authorize URL）、`GET /callback`（處理 authorization code）、`GET /status`（顯示是否已連線）、`POST /revoke`（清除 token）
  - `banks.py` — `GET /banks`（列出 + 狀態）、`PUT /banks/{code}`（toggle enabled）
  - `secrets.py` — `GET /secrets`（列出已設定的 bank code，**不回密碼明文**）、`PUT /secrets/{code}`（設定加密密碼）、`DELETE /secrets/{code}`、`POST /secrets/import-from-env`（一鍵匯入）
  - `admin.py` — `GET /admin/token-info`（last-4 + created_at）、`POST /admin/token-rotate`（產新 token、舊 session 失效）
- DB 模型擴增：
  - `bank_settings` 表（`code` PK, `enabled`, `display_name`, `notes`, `created_at`, `updated_at`）— SSOT 取代 `banks.yaml` 的 `enabled` 欄位；`banks.yaml` 仍保留銀行靜態元資料（parser 對應、欄位 schema）。
  - `bank_secrets` 表（`bank_code` PK, `encrypted_password`, `created_at`, `updated_at`）— 加密儲存 PDF 密碼。
  - `gmail_oauth_state` 表（`state` PK, `code_verifier`, `created_at`）— OAuth Web flow PKCE 暫存，10 分鐘過期。
- **加密機制**：新增 `${CCAS_DATA_LOCATION}/secrets/master.key`（Fernet 32-byte URL-safe base64）：entrypoint 啟動時若該檔不存在，自動產生（權限 0600）並寫入；存在時讀取載入記憶體。Decryptor 使用該 key 解密 `bank_secrets.encrypted_password`。`master.key` SHALL **不**入 git、SHALL 隨 `${CCAS_DATA_LOCATION}` 備份。
- **設定來源優先序變更**（重要）：PDF 密碼解析順序 SHALL 為 `bank_secrets` (DB) → `PDF_PASSWORD_*` (env) → 無密碼。Bank enabled 解析順序 SHALL 為 `bank_settings` (DB) → `banks.yaml.enabled` → 預設 enabled。**env / yaml 仍為 fallback，不刪除**，避免破壞既有部署、保留 dev-only 簡便路徑。
- **install-quickstart 連動更新**：原誠實揭露段落（`PDF_PASSWORD_*` 手填、`banks.yaml` 手編、`gmail-setup.md` CLI flow）SHALL 在本 change 落地後改寫，引導使用者改用 `/setup/*` UI；CLI flow 仍保留作為 advanced / fallback 路徑。

不在本 change 範圍內：
- **多 user / RBAC**：本 change 仍維持「single API token = single user」設計，admin 概念僅限「token rotate」一件事，不引入 role / permission 表。多 user 列為後續 enhancement。
- **Telegram bot 設定 UI**：本 change 不做。Telegram token 仍走 env、由 `compose-pull-deploy/D10` 規範。
- **2FA / OAuth provider 自架**：本 change Gmail OAuth 直接用 Google，不引入自家 OAuth server。

## Capabilities

### New Capabilities

- `gmail-oauth-web`：使用者透過瀏覽器完成 Gmail OAuth 授權（取代 host CLI），含 credentials.json 上傳、authorize redirect、callback 換 token、狀態顯示、revoke 操作。
- `bank-management-ui`：使用者於 `/setup/banks` 啟用 / 停用各銀行，狀態存於 DB 取代手編 `banks.yaml`；含每銀行已收 PDF 數、最後 parse 時間等可見性指標。
- `pdf-secrets-ui`：使用者於 `/setup/secrets` 設定各銀行 PDF 密碼，密碼以 Fernet 加密存於 DB，含 master key 自動產生、env 一鍵匯入、解密優先序明文化。
- `admin-token-rotate-ui`：使用者於 `/setup/admin` 旋轉 API token，舊 token / cookie session 立即失效；含 token last-4 顯示與 created_at audit trail。

### Modified Capabilities

- `installation-quickstart`（compose-pull-deploy 已建立）：原「目前仍需手動設定的項目」章節 SHALL 改寫指引使用者改走 `/setup/*` UI；CLI / yaml 編輯仍保留作為 fallback。
- `pipeline-orchestration`（pipeline-operations-center 既有 capability）：ingest / decrypt / classify 階段 SHALL 從 `bank_settings` 讀 enabled 狀態、從 `bank_secrets` 讀解密密碼，env / yaml 為 fallback。

## Impact

- **新檔案**：
  - 後端：`backend/src/ccas/api/routers/setup/{__init__,gmail,banks,secrets,admin}.py`、`backend/src/ccas/storage/secrets.py`（master key + Fernet helper）、`backend/alembic/versions/<ts>_add_setup_tables.py`
  - 前端：`frontend/src/pages/setup/{gmail,banks,secrets,admin}.tsx`、`frontend/src/pages/setup/layout.tsx`（共用導覽）、對應 `*.test.tsx`、`frontend/e2e/setup.spec.ts`
- **修改**：
  - `backend/src/ccas/storage/models.py`（新增三個模型）
  - `backend/src/ccas/decryptor/passwords.py`（密碼解析優先序：DB → env）
  - `backend/src/ccas/ingestor/job.py` 與 `parser/job.py`（bank enabled 檢查改走 `bank_settings`）
  - `backend/src/ccas/ingestor/gmail_client.py`（token / credentials 路徑改從 settings 讀，但仍允許 env override）
  - `scripts/docker-entrypoint.sh`（master key 自動產生段落）
  - `frontend/src/App.tsx`（lazy routes）、`frontend/src/components/layout.tsx`（NAV 新增「設定中心」）
  - `docs/install-quickstart.md`（指引改走 `/setup/*`、保留 CLI fallback 段落）
  - `docs/gmail-setup.md`（GCP Console 步驟保留、加入「Web flow 取代 CLI」章節）
- **DB 變更**：新增 `bank_settings`、`bank_secrets`、`gmail_oauth_state` 三表，皆為加表、無破壞性，回滾 = drop tables。
- **Runtime 依賴**：新增 `cryptography`（Fernet）— 此套件已是 SQLAlchemy / passlib 等的常見 transitive dependency，pyproject `--group api` 顯式宣告版本下限。前端可能需 `pnpm dlx shadcn add switch input-otp file-input`（如未裝）。
- **API token 行為變更**：rotate 後舊 token / cookie 立即失效（改變既有行為）。docs SHALL 明示此語意。
- **既有部署相容性**：env `PDF_PASSWORD_*` 與 `banks.yaml.enabled` 仍為 fallback，既有部署升級後不需動 env、行為不變；首次進 `/setup/secrets` 時系統提示「匯入並清除 env」可選擇性啟用。
- **後續 change 銜接**：`bills-management-and-insights` 假設 `/setup/*` 已存在（讓使用者能在同一個「設定」區管理規則 / 預算 / 提醒），但兩 change 程式碼層正交可平行，僅 NAV 與設定中心 layout 需協調。
