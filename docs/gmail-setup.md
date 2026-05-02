# Gmail OAuth 設定指南

CCAS 從 Gmail 收取信用卡帳單 PDF，需要使用者授權 OAuth。本文件說明如何在 Google
Cloud Console 取得 `credentials.json` 並完成首次 token 授權。

> **規劃中**：下一個 change `oauth-onboarding-ui` 將提供 `/setup/gmail` Web 頁面，
> 在瀏覽器內完成所有 OAuth 步驟（含 credentials 上傳與 token 取得），屆時可省略本文。
> 當前版本仍需手動操作 Google Cloud Console 與 CLI。

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

### A.4 建立 OAuth client ID

1. APIs & Services → **Credentials** → 點上方「+ Create Credentials」→ **OAuth client ID**
2. Application type: **Desktop app**（重要：不要選 Web application）
3. Name: `CCAS Desktop`
4. 建立後跳出 client_id / client_secret，**下載 JSON** → 存成 `credentials.json`

---

## B. 取得 `token.json`（首次 OAuth 授權）

### 方式 1：使用 CLI（當前可用）

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

### 方式 2：Web UI（規劃中，`oauth-onboarding-ui` change）

未來版本將支援：
1. 開瀏覽器至 `/setup/gmail`
2. 點「上傳 credentials.json」
3. 點「開始授權」→ 自動完成 OAuth dance
4. 連線狀態顯示 connected

無需 host 端 CLI。

---

## C. 部署到 Docker

prod 部署時將兩個檔案放入 `${CCAS_DATA_LOCATION}`（預設 `./data`）：

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

OAuth refresh token 有效期長（目前 6 個月，Google 不定期調整）。過期後執行：

```bash
rm backend/data/token.json   # 或 ${CCAS_DATA_LOCATION}/token.json
cd backend && uv run python -m ccas.tools.gmail_auth   # 重跑
```

### Q: OAuth 授權頁出現「未驗證的 app」警告

這是 External + 未送審的正常行為。點「Advanced → Go to CCAS (unsafe)」即可。
個人使用沒問題；若要對外提供，需走 OAuth verification 流程（含安全審查）。

### Q: 換了 Google 帳號要重新授權？

是。token.json 綁定特定帳號。要改用另一個 Gmail：刪除 token.json + 重跑 `gmail_auth`。

### Q: scope 改了之後 token 是否要重新產生？

是。Gmail API scope 變動會讓既有 token invalid，須刪除 token.json 重跑授權。

---

## E. 安全性提醒

- **`credentials.json`** 含 OAuth client_secret，不應 commit 到任何 repo（CCAS 已 gitignore）
- **`token.json`** 含 refresh token，等同 Gmail 完整存取權；嚴守 0600 權限、不外傳
- 兩份檔案皆隨 `${CCAS_DATA_LOCATION}` 一同備份，使用 [upgrade-guide.md](upgrade-guide.md)
  的 tar 備份流程即可保留 OAuth 狀態
