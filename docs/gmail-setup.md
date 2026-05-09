# Gmail OAuth 設定指南

CCAS 從 Gmail 收取信用卡帳單 PDF，需要使用者授權 OAuth。本文件說明如何在 Google
Cloud Console 取得 `credentials.json`，並使用 `/setup/gmail` Web flow 完成 token 授權。

---

## A. 在 Google Cloud Console 建立 OAuth 憑證

### A.1 建立或選擇 GCP project

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 頂部專案下拉 → 「**新增專案**」
3. 名稱填 `ccas-personal`（或任意），組織留空，點建立

### A.2 啟用 Gmail API

1. 左側選單 → APIs & Services → **Library**
2. 搜尋「Gmail API」→ 點進去 → **啟用**

### A.3 設定 OAuth consent screen

1. APIs & Services → **OAuth consent screen**
2. User Type 選 **External**（個人 Google 帳號用此）→ 建立
3. App information：
   - App name: `CCAS`
   - User support email: 你自己的信箱
   - Developer contact: 同上
4. Scopes 區段：點 **Add or remove scopes**，搜尋並勾選：
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`（CCAS 會標記已處理的信件）
5. **Test users**：點「+ Add Users」→ 填入要授權的 Gmail（即你自己），存檔
   - 不送上架審查時 OAuth 限「test users」最多 100 人，個人使用足夠

### A.4 建立 OAuth client ID（Web flow 推薦）

1. APIs & Services → **Credentials** → 點上方「+ Create Credentials」→ **OAuth client ID**
2. Application type: **Web application**
3. Name: `CCAS Web`
4. Authorized redirect URIs 加入你的 CCAS callback：
   - 預設：`http://localhost:8080/setup/gmail/callback`
   - 若 `.env` 設 `CCAS_PORT=12283`：`http://localhost:12283/setup/gmail/callback`
   - 若使用網域：`https://ccas.example.com/setup/gmail/callback`，並同步設定 `.env` 的 `PUBLIC_BASE_URL`
5. 建立後下載 JSON → 存成 `credentials.json`

> CLI fallback 可另外建立 **Desktop app** client；Web flow 建議使用 Web application，redirect URI
> 才能明確綁到 `/setup/gmail/callback`。

---

## B. 取得 `token.json`（首次 OAuth 授權）

### 方式 1：Web flow（推薦）

1. 啟動 CCAS 並登入 Web UI
2. 開啟 `http://localhost:${CCAS_PORT:-8080}/setup/gmail`
3. 上傳從 Google Cloud Console 下載的 `credentials.json`
4. 確認頁面顯示的 redirect URI 已存在於 OAuth client 的 Authorized redirect URIs
5. 點「授權 Google」，在 Google consent 頁同意 Gmail 權限
6. Google 會導回 `/setup/gmail/callback`，成功後頁面顯示 connected

Web flow 會把 token 寫入 `GMAIL_TOKEN_PATH`（prod 預設 `/data/token.json`），不用在 host
機器執行 Python CLI。

> **必須先登入 CCAS 再點授權**：步驟 1 的「登入 Web UI」是 web flow 的硬性前置。
> 若你直接在外部瀏覽器貼 OAuth URL（例如把 `/api/setup/gmail/authorize` 回傳的
> `authorize_url` 複製到全新瀏覽器），Google consent 後會跳回 `/setup/gmail/callback`，
> 但 SPA 的 `/setup/*` 路由受 auth guard 保護 — 沒登入就會被踢回 `/login`，前端 callback
> 元件來不及把 `?code/state` 轉發給 backend，token.json 不會寫入，DB 裡的 state row 也
> 不會被消化。**正確流程**：先到 `/login` 用 API token 完成登入，再從 `/setup/gmail` 點
> 「授權 Google」按鈕觸發整段流程。

### 方式 2：CLI fallback

```bash
# 在 repo 根目錄
cp /path/to/downloaded.json backend/data/credentials.json
cd backend
uv run python -m ccas.tools.gmail_auth
```

腳本會：
1. 開啟瀏覽器至 Google 授權頁
2. 你選擇 Gmail 帳號 → 同意 readonly + modify scope
3. 瀏覽器導回 localhost，token 落地至 `backend/data/token.json`

CLI 適用於無 GUI 或暫時無法設定 Web redirect URI 的環境；一般安裝請優先使用 Web flow。

---

## C. 部署到 Docker

使用 Web flow 時只需要在 `/setup/gmail` 上傳 `credentials.json`。若使用 CLI fallback，請將兩個檔案放入 `${CCAS_DATA_LOCATION}`（預設 `./data`）：

```bash
mkdir -p ./data
cp credentials.json ./data/credentials.json
cp token.json ./data/token.json   # 由方式 1 產生
chmod 600 ./data/credentials.json ./data/token.json
```

在 `.env` 確認路徑（多數情況不需要動，使用預設）：

```env
GMAIL_CREDENTIALS_PATH=/data/credentials.json
GMAIL_TOKEN_PATH=/data/token.json
```

> 路徑為**容器內**絕對路徑；`/data` 由 compose 掛載至 host 端的 `${CCAS_DATA_LOCATION}`。

---

## D. 常見問題

### Q: token.json 過期了

OAuth refresh token 有效期長（目前 6 個月，Google 不定期調整）。過期後建議進
`/setup/gmail` 點 revoke 後重新授權；CLI fallback 可執行：

```bash
rm backend/data/token.json   # 或 ${CCAS_DATA_LOCATION}/token.json
cd backend && uv run python -m ccas.tools.gmail_auth   # 重跑
```

### Q: OAuth 授權頁出現「未驗證的 app」警告

這是 External + 未送審的正常行為。點「Advanced → Go to CCAS (unsafe)」即可。
個人使用沒問題；若要對外提供，需走 OAuth verification 流程（含安全審查）。

### Q: 換了 Google 帳號要重新授權？

是。token.json 綁定特定帳號。要改用另一個 Gmail：進 `/setup/gmail` revoke 後重新授權；
CLI fallback 則刪除 token.json + 重跑 `gmail_auth`。

### Q: scope 改了之後 token 是否要重新產生？

是。Gmail API scope 變動會讓既有 token invalid，須透過 `/setup/gmail` 重新授權。

### Q: 出現 `redirect_uri_mismatch`

代表 Google OAuth client 沒有加入目前 CCAS 顯示的 callback URL。回到
Google Cloud Console → APIs & Services → Credentials → 你的 OAuth client →
Authorized redirect URIs，加入 `/setup/gmail` 頁面顯示的完整 redirect URI。

---

## E. 安全性提醒

- **`credentials.json`** 含 OAuth client_secret，不應 commit 到任何 repo（CCAS 已 gitignore）
- **`token.json`** 含 refresh token，等同 Gmail 完整存取權；嚴守 0600 權限、不外傳
- 兩份檔案皆隨 `${CCAS_DATA_LOCATION}` 一同備份，使用 [upgrade-guide.md](upgrade-guide.md)
  的 tar 備份流程即可保留 OAuth 狀態
