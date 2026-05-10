## Context

CCAS 目前的設定路徑分散在三個介面：

| 設定項目 | 既有介面 | 痛點 |
|---|---|---|
| Gmail credentials | host file system + CLI | 必須有 GCP Console + host shell + python 環境 |
| Gmail token | host CLI（`localhost:0` callback） | container 內無法執行；新 OAuth scope 變更要重跑 |
| 銀行啟用 | `config/banks.yaml` | 重啟 backend 才生效；改 yaml 容易壞 schema |
| PDF 密碼 | `.env` 的 `PDF_PASSWORD_<BANK>` | 明文 env、新增需 compose down/up；多人/多卡時 env 越長越亂 |
| API token | `${CCAS_DATA_LOCATION}/secrets/api-token` | 換 token 要 SSH 進機器或 docker exec |

`compose-pull-deploy` 已釘清此 change 必須處理 (a)(b)(c)(d) 四件事。本 change 設計重點：**讓「設定」成為 web app 第一等公民，使用者除了首次部屬與升級之外不需要回到 terminal**。

設計約束：
- 既有部署不能斷：env / yaml 必須保留為 fallback，DB 為新 SSOT 但缺資料時平滑降級。
- master key 不能用 env：env 任何時刻都能被 docker inspect 讀到，違背「敏感資料加密」承諾。必須用獨立檔案。
- 單人本機自架：不引入 RBAC 也不引入 OAuth server，token 就是 single source of authentication。
- Backend 與 worker 共享同一 data volume（compose-pull-deploy/D5 已強制），master.key 與 DB 都在 `${CCAS_DATA_LOCATION}` 子目錄，跨 process 一致性自動成立。

## Goals / Non-Goals

**Goals:**
- 使用者部屬完 → 進 dashboard → 在 `/setup/*` 完成 Gmail 連線、銀行啟用、PDF 密碼設定、token rotate，全程不需要 terminal、文字編輯器、GCP Console（除了首次拿 `credentials.json`）。
- env / yaml fallback 保留，既有 dev / prod 部署升級後行為不變；新使用者預設走 DB SSOT。
- PDF 密碼明文不離開 backend memory；DB 與備份檔皆為加密內容。
- Token rotate 後舊 token 立即失效，避免使用者誤以為「rotate 但舊 token 還能用」。
- Gmail OAuth Web flow 用 PKCE（authorization code + code challenge），不用 client secret，與 Google 公開的 Desktop / Web app flow 一致。

**Non-Goals:**
- 多 user / RBAC（單 token = 單 user）
- Telegram bot 設定 UI
- 自架 OAuth server / SSO 整合
- master key rotation UI（首次產生即固定，列為後續 enhancement）
- 跨機器同步 secrets（單機自架）
- credentials.json 直接從 GCP API 自動建立（需要使用者授權 GCP Cloud SDK，過度工程）

## Decisions

### D1：Gmail OAuth Web flow 採「使用者瀏覽器即 client」、credentials.json 仍由使用者上傳

選擇：使用者於 `/setup/gmail` 上傳 `credentials.json`（從 GCP Console 下載的檔案）→ 後端讀 client_id / client_secret 暫存於 `${CCAS_DATA_LOCATION}/gmail/credentials.json` → 前端點「授權 Google」按鈕 → 後端產生 PKCE code_verifier + state、寫入 `gmail_oauth_state` 表、回傳 Google authorize URL → 瀏覽器跳轉 Google consent → Google redirect 回 `${proxy}/setup/gmail/callback?code=...&state=...` → 後端驗證 state、用 code 換 token、寫 `${CCAS_DATA_LOCATION}/gmail/token.json` → 前端輪詢 `/api/setup/gmail/status` 看到 connected。

替代方案考慮：
- **Device flow**（IoT / TV 慣用）：被否決，Google 對 Gmail scope 不支援 device flow，必須走 authorization code。
- **後端內建公用 OAuth client**（CCAS 自架 OAuth client，使用者不用上傳 credentials.json）：被否決。需要 CCAS 維護 OAuth client、處理 quota / abuse；Google 對「Gmail readonly」scope 的 OAuth verification 流程冗長（CASA tier 2 audit），單人自架軟體無法負擔。
- **CLI 維持唯一路徑**：被否決，違背 change 主目標。

理由：使用者已經有 `credentials.json`（compose-pull-deploy 的 docs/gmail-setup.md 指引產生），本 change 只是把「換 token」這一步從 CLI 搬到 Web。OAuth `redirect_uri` 在 GCP Console 端設定為 `http://localhost:${CCAS_PORT}/setup/gmail/callback`，使用者首次設定時 docs 引導加入此 URL；若使用者改 `CCAS_PORT`，docs 提示要回 GCP Console 同步更新 redirect URI。

### D1.1：OAuth state PKCE 與 redirect 驗證

選擇：
- 產生 `code_verifier`（128-byte URL-safe random）+ `state`（32-byte URL-safe random），雙寫入 `gmail_oauth_state` 表，TTL 10 分鐘。
- callback 時驗證 state 存在且未過期；用 code_verifier + authorization code 換 token；成功後刪除 state row。
- redirect_uri 由 backend 從 `Settings.public_base_url`（新增 env，預設 `http://localhost:${CCAS_PORT}`）組成；不接受 query 動態 redirect。

理由：Google 強制 PKCE，狀態管理走 DB 而非 in-memory（因為 backend 與 worker 都可能重啟，但 OAuth flow 必須在 10 分鐘內完成），已在合理工程範疇。

### D2：bank_settings 表為 enabled 狀態 SSOT，banks.yaml 退回靜態元資料

選擇：
- 新表 `bank_settings`（`code` PK, `enabled` bool, `display_name`, `notes`, `updated_at`）。
- `banks.yaml` 保留銀行靜態元資料（parser 對應、欄位 schema、是否 require password），不再持有 `enabled` 欄位；現有 yaml 的 `enabled` 欄位讀取邏輯 SHALL 改為「DB 有就用 DB、否則 fallback yaml.enabled、否則預設 true」。
- `bank_settings` 首次啟動由 entrypoint seed：對 `banks.yaml` 中所有銀行建立預設 row（enabled=true）。

替代方案考慮：
- **直接動 banks.yaml**：被否決，yaml 是 git-tracked 靜態元資料，運行期改動會造成 git diff 噪音、且 worker / scheduler / bot 重啟才感知到變更。
- **enabled 仍在 yaml、UI 改 yaml 檔**：被否決，並發寫 yaml + parser schema 驗證複雜，DB 是更好的運行期狀態載體。

理由：靜態元資料（哪家銀行、用哪個 parser）放 yaml；運行期狀態（要不要跑、密碼是什麼）放 DB。這是 SSOT 拆分的標準做法。

### D3：bank_secrets 用 Fernet 加密、master.key 自動產生並落地 secrets 目錄

選擇：
- `bank_secrets.encrypted_password` 為 base64 encoded Fernet ciphertext（含 timestamp + HMAC + AES-128-CBC）。
- master key 為 Fernet 32-byte URL-safe base64，存於 `${CCAS_DATA_LOCATION}/secrets/master.key`，權限 0600。
- entrypoint 啟動順序：(1) 確保 secrets 目錄存在 → (2) 偵測 `master.key` 不存在則 `Fernet.generate_key()` 寫入、stdout 印 `[INFO] 已自動產生 master.key（首次啟動）` → (3) 後續 token bootstrap 與 alembic migration。
- backend / worker / scheduler / bot 啟動時都載入同一份 master.key（共用 data volume）；從 `Settings.master_key`（新增 cached property，從 file 讀取）取得。

替代方案考慮：
- **master key 從 env 讀**：被否決。env 任何時刻可被 docker inspect / proc filesystem 讀取，與「加密儲存」承諾自相矛盾。
- **每銀行一把獨立 key**：被否決，過度工程，使用者只是想避免明文 PDF 密碼，不需要 per-bank key isolation。
- **使用者自己提供 key**：被否決，違背「自動化、零摩擦」原則；可作為 future enhancement（KMS integration）。

理由：Fernet 是 cryptography 套件官方推薦的「對稱加密 + 認證」primitive，比手寫 AES + HMAC 安全；master.key 落地檔案 + 0600 權限 + 與 data 同備份是業界 self-host 慣例（Bitwarden self-host、Vaultwarden 等同樣設計）。

### D3.1：env `PDF_PASSWORD_*` 與 DB 的解析優先序

選擇：解析順序 SHALL 為 `bank_secrets`（DB）→ `PDF_PASSWORD_<CODE>`（env）→ 無密碼。

替代方案考慮：
- **env 優先**：被否決。使用者設定 UI 改密碼後若 env 仍為舊值，會「UI 看似改了但實際沒生效」，違反最小驚奇。
- **強制刪 env**：被否決，破壞既有部署相容性。

理由：DB 為新 SSOT，env 為 fallback。`/setup/secrets` 頁面 SHALL 顯示「目前生效來源」（DB / env），讓使用者明確知道哪些密碼來自 env、哪些來自 DB。

### D3.2：env 一鍵匯入並清除 env 的權衡

選擇：UI 提供「匯入 N 個 env 密碼到 DB」按鈕，**只匯入不刪除 env**。docs 明示「DB 已優先生效，env 可在下次 `.env` 編輯時手動移除」。

替代方案考慮：
- **匯入並自動寫回 .env 移除**：被否決。entrypoint 不應寫使用者的 `.env`（D11 已釘原則），且 docker compose 環境下 .env 可能不在 container 可寫位置。
- **匯入後直接以 DB 為唯一 source（env 留著但不讀）**：被否決。env 仍要保留為 fallback，避免新環境忘記設 DB 時無密碼。

理由：簡單可逆 — 使用者可隨時在 UI 刪除 DB 條目讓 env 重新生效。

### D4：API token rotate 立即失效舊 token 與舊 cookie

選擇：
- `POST /api/setup/admin/token-rotate` 後端流程：
  1. 產生新 hex（與 D11 同邏輯）
  2. 寫入 `${CCAS_DATA_LOCATION}/secrets/api-token`（覆寫，權限 0600）
  3. **重置 backend in-memory `Settings.api_token` cache**，後續 `verify_token` 用新 token
  4. 增加 `api_token.token_version`（新欄位 `secrets/api-token-version`，純整數），任何 active cookie session（payload 內含當時 token_version）SHALL 在後續 request 被認定為失效
  5. response 回新 token 明文一次（前端顯示給使用者抄寫）
- 前端在 rotate 成功後 SHALL 立即清除自己的 cookie session、redirect 至 `/login`、提示「請用新 token 登入」。

替代方案考慮：
- **rotate 後仍允許舊 cookie session 到期前繼續用**：被否決。違反 rotate 語意（rotate 表示「立即作廢舊憑證」）；攻擊情境下 rotate 是補救手段，不能讓舊 token 還能用。
- **token_version 寫進 DB 而非 file**：可行，但 cookie session 驗證走 backend in-memory cache + file，不走 DB 才能在「DB 連線異常時仍能拒絕舊 token」。
- **改用 JWT + refresh token**：被否決，過度工程，與 single-token 設計衝突。

理由：rotate 是低頻操作（一年數次以內），語意正確優先於 UX 流暢。

### D5：admin user 概念極簡化 — 不引入 user 表

選擇：本 change **不**新增 `users` 表，沒有 username / password / email。`/setup/admin` 頁僅顯示：
- 目前 token last-4 chars（`...a3f9`）
- token created_at（從 file mtime 取）
- 「產生新 token」按鈕（rotate）

替代方案考慮：
- **同時引入 admin email / password**：被否決，與 single-token 設計衝突，且本 change 沒有寄信能力（無 SMTP 配置）。
- **加入 OTP**：被否決，需要 user 表 + secret storage，過度工程。

理由：保持 single-token 設計，本 change 只兌現「在 UI rotate token」承諾，不擴張 auth model。多 user 列為後續 enhancement，屆時再引入 users 表。

### D6：`/setup/*` 路由與 layout 設計

選擇：
- 新增 `frontend/src/pages/setup/layout.tsx` 共用「設定中心」側邊導覽（gmail / banks / secrets / admin），內嵌於主 layout 之內（共用頂部 header 與 nav）。
- 主 layout `NAV_ITEMS` 新增「設定中心」項，icon `Settings2`，連到 `/setup/gmail`（預設子頁）。
- 既有 `/settings`（API token 顯示）整併進 `/setup/admin`，舊 `/settings` route 改為 redirect 到 `/setup/admin`。

替代方案考慮：
- **`/setup` 為獨立 standalone layout（無主 nav）**：被否決，使用者進入後找不到回 dashboard 的路徑，UX 不順。
- **`/setup` 與 `/settings` 並存**：被否決，命名重疊使用者混淆。

理由：「設定中心」是 sub-app，仍屬於 dashboard 的一部分；舊 `/settings` 整併保留 backward-compat（避免外部書籤失效）。

### D7：bank_settings 與 banks.yaml 的 seed 流程

選擇：entrypoint 在 alembic migration 之後新增 seed 階段：
1. 讀 `${CCAS_CONFIG_LOCATION}/banks.yaml` 全部 banks
2. 對每個 bank 在 `bank_settings` 用 INSERT OR IGNORE（SQLite）/ ON CONFLICT DO NOTHING（標準 SQL）建立預設 row（enabled = yaml.enabled，預設 true）
3. yaml 中已不存在的 bank（使用者刪掉 yaml 條目）SHALL **不**自動刪除 DB row，避免 enabled 狀態遺失；而是在 `/setup/banks` UI 顯示「孤兒」標記讓使用者手動處理。

理由：避免 yaml 與 DB 雙寫衝突；yaml 為靜態元資料，DB 為運行期狀態，兩者不互相覆寫。

### D8：gmail_oauth_state 表 TTL 10 分鐘 + 啟動時清理

選擇：
- 表結構：`state` PK, `code_verifier`, `created_at`。無 `expires_at`，TTL 由 callback 時計算 `now - created_at > 10min` 決定。
- entrypoint 啟動時順手 `DELETE FROM gmail_oauth_state WHERE created_at < NOW() - INTERVAL '1 day'`（SQLite 用 datetime 比較），避免長期積累。
- callback 處理成功後立即刪除該 state row（一次性使用）。

理由：OAuth state 是短暫資料，DB 不需要 cron 清理工具。

## Risks / Trade-offs

- **master.key 遺失 = 所有加密 PDF 密碼遺失**：[Risk] 使用者誤刪 secrets 目錄會永久失去解密能力。Mitigation：(a) docs 強烈建議備份 `${CCAS_DATA_LOCATION}` 整個目錄、(b) `/setup/secrets` 頁顯示「master.key 是備份的關鍵」warning banner、(c) `Fernet` 解密失敗時 backend SHALL 回 clear error 訊息（「master.key 與加密資料不匹配，請確認備份完整」），不要讓使用者誤以為密碼錯。
- **Gmail OAuth redirect URI 與 CCAS_PORT 耦合**：[Risk] 使用者改 `CCAS_PORT=12283` 後 OAuth redirect URI 必須在 GCP Console 同步更新，否則 callback 會 redirect_uri_mismatch。Mitigation：`/setup/gmail` 頁面「授權 Google」按鈕之前 SHALL 顯示「目前 redirect URI 為 `http://localhost:${CCAS_PORT}/setup/gmail/callback`，請確認 GCP Console 已加入此 URL」。docs/gmail-setup.md 同步說明。
- **OAuth Web flow 強制 host 是 localhost**：[Risk] 使用者透過 Tailscale / 自架 reverse proxy 暴露 CCAS 到 LAN 或公網時，redirect_uri 仍要符合 GCP Console 設定。Mitigation：新增 env `PUBLIC_BASE_URL`（預設 `http://localhost:${CCAS_PORT}`），允許使用者改為 `https://ccas.mydomain.com`，docs 教學 GCP Console 加多個 redirect URI。
- **token rotate 後忘記抄寫新 token = 鎖死自己**：[Risk] 使用者點 rotate、看到新 token 但沒抄寫、cookie 已失效 → 無法登入。Mitigation：(a) UI 顯示新 token 時 SHALL 預設複製到剪貼簿、(b) 顯示時 SHALL 含「請先驗證能登入再關閉此頁」提示、(c) 使用者真鎖死時可以 `docker compose exec backend cat /data/secrets/api-token` 救回（docs 記錄此 fallback）。
- **DB 升級遷移期間 env fallback 行為差異**：[Risk] 升級後首次啟動，bank_settings 已 seed 但 bank_secrets 為空，使用者既有 env `PDF_PASSWORD_*` 仍生效；若使用者後續刪除 env 但忘了在 UI 設定，下次 pipeline 跑 decryption 會失敗。Mitigation：`/setup/secrets` 頁初次進入 SHALL 顯示「偵測到 env 中有 N 個密碼但 DB 尚未匯入，是否一鍵匯入？」橫幅，引導使用者明確完成遷移。
- **UI 上傳 credentials.json 含 client_secret 為敏感資料**：[Risk] credentials.json 含 OAuth client_secret，若 web 上傳過程被 MITM → 洩漏。Mitigation：(a) 強制要求 prod 走 https（透過外部 TLS 終結器，CCAS 不負責 TLS）、(b) credentials.json 寫入 data 目錄時權限 0600、(c) docs 警告「不要在公開網路使用 http 傳輸 credentials.json」。
- **rotate 與並發 worker / scheduler 的 race**：[Risk] rotate 同時 worker / scheduler 正執行需要 token 的內部 call → 用到舊 token 失敗。Mitigation：所有需要 verify_token 的呼叫都從 `Settings.api_token` 動態讀取（不快取進 closure）；worker / scheduler 內部不打 backend HTTP API（既有設計），所以實際 race window 僅 frontend → backend，rotate 後 frontend 已被踢出，不會有 race。
- **bank_settings 與 yaml 雙重維護負擔**：[Risk] 開發者新增銀行時要記得同步 yaml + seed entrypoint。Mitigation：seed 邏輯設計為「yaml 為唯一新增來源、DB 自動跟進」，開發者只需改 yaml；UI 端顯示「孤兒」處理已存在但 yaml 已移除的條目。

## Migration Plan

1. **平行落地**：本 change 與 `compose-pull-deploy`、`pipeline-operations-center` 並行不衝突；建議在 `compose-pull-deploy` 先合入後再啟動本 change（為 `${CCAS_DATA_LOCATION}/secrets/` 目錄結構與 master.key 機制需要 entrypoint 已支援）。
2. **DB migration**：alembic 加表（三張新表），無破壞性。回滾 = drop tables + 刪除 master.key 檔（後者使用者手動）。
3. **既有部署升級路徑**：
   - 升 image → `docker compose up -d` → entrypoint 自動建立 master.key、跑 alembic、seed bank_settings → 既有 env `PDF_PASSWORD_*` 仍生效（fallback）→ 使用者進 `/setup/secrets` 看到「偵測 env 密碼，是否匯入」橫幅 → 自行決定何時遷移。
   - 既有 `banks.yaml.enabled` 立即被 `bank_settings` 接管（首次 seed 時讀 yaml.enabled 寫入 DB）；之後再改 yaml 不影響運行期狀態。
4. **回滾**：alembic downgrade（drop tables）→ 重啟 backend → 系統 fallback 回 env / yaml，既有設定無資料遺失。`master.key` 檔可保留供下次 re-enable。
5. **Docs 同步**：本 change 落地時 SHALL 同步更新 `install-quickstart.md`「目前仍需手動設定的項目」章節為「於 `/setup/*` 完成設定」。

## Open Questions

- 是否在 `/setup/admin` 加入「目前已連線的 cookie session 數量」顯示？— 列為 future enhancement，需要 session store。本 change 不做。
- master.key 如果使用者真的遺失，是否提供「重置加密」選項（清除所有 bank_secrets）？— 列為 future enhancement，需要明確的「我知道會永久遺失密碼」確認流程。本 change 預設不提供。
- Gmail OAuth scope 變更時的 re-consent UI 如何呈現？— 本 change 預設不變更 scope（沿用既有 `gmail.readonly` 等），未來增 scope 時設計 re-consent flow，列為 future enhancement。
- `PUBLIC_BASE_URL` 是否要與 `compose-pull-deploy` 既有 `FRONTEND_ORIGINS` 統一？— 兩者用途不同（前者 OAuth redirect、後者 CORS allow），保持分開；docs SHALL 註明同步更新慣例。
