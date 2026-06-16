# CCAS 快速安裝（Docker Compose / pull-only）

本文件針對「想在本機快速跑起 CCAS 帳單自動化、不打算自行 build」的使用者；只需要下載
`docker-compose.yml` + `example.env` 兩個檔案即可啟動。

> **本路徑為兩種啟動方式之一**：
> - **dev（含原始碼）**：見 [docs/developer-guide.md](developer-guide.md)，根目錄 `docker-compose.yaml` + override
> - **prod（pull-only）**：本文，`docker/docker-compose.yml` 純 image
>
> **prod self-build 中間路徑（在根目錄 compose 上 `--target production`）已棄用**。如需本機驗證 production image，請改用 `CCAS_VERSION=local` 搭配 prod compose（見「進階：自建本機 image」段落）。

---

## 步驟 0：準備 Gmail OAuth credentials（必做）

CCAS 需要從你的 Gmail 收取信用卡帳單 PDF。先到 Google Cloud Console 建立 OAuth client
並下載 `credentials.json`；token 授權可在服務啟動後透過 `/setup/gmail` 完成。

完整步驟見 [docs/gmail-setup.md](gmail-setup.md)（建立 GCP project → 啟用 Gmail API →
設定 OAuth consent screen → 建立 OAuth client → 下載 credentials.json）。

## 步驟 1：建立工作目錄

```bash
mkdir ~/ccas && cd ~/ccas
```

## 步驟 2：下載 release artifacts

從 [GitHub Releases](https://github.com/<owner>/ccas/releases/latest) 下載最新版的
`docker-compose.yml` 與 `example.env`：

```bash
RELEASE=v0.4.0   # 改為要安裝的精確版號
curl -fsSL -o docker-compose.yml \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/docker-compose.yml"
curl -fsSL -o example.env \
  "https://github.com/<owner>/ccas/releases/download/${RELEASE}/example.env"

cp example.env .env
```

## 步驟 3：編輯 `.env`

至少需填妥：

| 變數 | 值 |
|---|---|
| `REPO_OWNER` | GHCR namespace（即 release 連結中的 `<owner>`） |
| `CCAS_VERSION` | 與 release tag 一致（例：`v0.1.0`） |

**可稍後在 Web UI 設定**：

- 各銀行 PDF 密碼：啟動後進 `/setup/secrets` 設定；env `PDF_PASSWORD_<BANK_CODE>` 仍是 fallback
- 銀行啟用清單：啟動後進 `/setup/banks` 切換；`config/banks.yaml` 仍是 fallback

**選填但常見**：

- `PUBLIC_BASE_URL`：OAuth redirect URI 使用；若改 `CCAS_PORT` 或使用自訂網域，請同步改成實際外部網址
- `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`：填妥則 bot 自動啟用，不需 `--profile`

> **自訂 `CCAS_PORT` 與 GCP redirect URI**：CCAS 使用的 redirect URI 為
> `${PUBLIC_BASE_URL}/setup/gmail/callback`，會隨 `PUBLIC_BASE_URL` / `CCAS_PORT` 動態切換。
> - 若 GCP OAuth client 是 **Desktop 類型**（`installed` block）：Google 的 loopback policy
>   接受任意 `localhost:PORT/path`，不需要在 GCP Console 加新 redirect URI。
> - 若 GCP OAuth client 是 **Web application 類型**（`web` block）：Google 嚴格比對 redirect URI。
>   切換 `CCAS_PORT` 時必須先在 GCP Console「APIs & Services → Credentials → OAuth 2.0
>   Client ID → Authorized redirect URIs」加入 `http://localhost:<NEW_PORT>/setup/gmail/callback`
>   後再啟動，否則授權會回 `Error 400: redirect_uri_mismatch`。

> `API_TOKEN` **可不填**：entrypoint 首啟會自動產生 32-byte token 並落地至
> `${CCAS_DATA_LOCATION}/secrets/api-token`（檔案權限 0600）。若顯式設為空字串會被驗證腳本擋下。

## 步驟 4：啟動

```bash
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
```

預期輸出：
```
[+] Running 7/7
 ✔ Container ccas-redis-1      Healthy
 ✔ Container ccas-backend-1    Healthy
 ✔ Container ccas-worker-1     Started
 ✔ Container ccas-scheduler-1  Started
 ✔ Container ccas-bot-1        Started
 ✔ Container ccas-frontend-1   Healthy
 ✔ Container ccas-proxy-1      Healthy
```

驗證：
```bash
curl -fsS "http://localhost:${CCAS_PORT:-8080}/api/health"
# {"status":"ok",...}
```

## 步驟 5：首次登入

CCAS 採「API token 即 Web UI 登入憑證」設計（首次部署不需要使用者帳號註冊）：

```bash
# 1) 取得自動產生的 token
cat ./data/secrets/api-token   # CCAS_DATA_LOCATION 對應路徑

# 2) 開啟瀏覽器
#    http://localhost:8080/login

# 3) 將上一步的 token 貼到輸入框送出
#    成功後即進入 dashboard

# 4) 如果接下來要進入 /setup/gmail 完成 Gmail 授權：
#    必須先完成步驟 3 登入，再從 UI 點「授權 Google」按鈕
#    （不要直接在外部瀏覽器貼 OAuth URL，否則 Google 跳回 /setup/gmail/callback
#     時 SPA auth guard 會把你踢回 /login，前端 callback 元件來不及把
#     ?code/state 轉發給 backend，token.json 不會寫入）
```

> 之後想換 token？進 `/setup/admin` 使用「產生新 token」。rotate 後舊 token 與舊 cookie
> 會立即失效，請先複製新 token 再登出。

---

## 步驟 6：進設定中心完成 onboarding

登入後從左側導覽進「設定中心」，依序完成：

| 頁面 | 用途 |
|---|---|
| `/setup/gmail` | 上傳 `credentials.json`、確認 redirect URI、點「授權 Google」、查看 connected 狀態或 revoke |
| `/setup/banks` | 啟用 / 停用銀行，查看已收 PDF 數與最後 ingest 時間 |
| `/setup/secrets` | 設定各銀行 PDF 密碼；密碼以 `master.key` 加密存入 DB，可一鍵匯入既有 env 密碼 |
| `/setup/admin` | 查看 token last-4 / version，旋轉 API token |

`/setup/secrets` 會永久顯示 master.key 備份提醒。請定期備份整個 `${CCAS_DATA_LOCATION}`
目錄；詳見 [secrets-management.md](secrets-management.md)。

---

## 步驟 7：個人化設定（選用）

完成 onboarding 後，可至下列頁面開啟「個人帳務管理」相關功能（詳細操作見
[docs/personal-rules-and-budgets.md](personal-rules-and-budgets.md)）：

| 頁面 | 用途 |
|---|---|
| `/insights` | 月趨勢、銀行對比、年度對比、商家排行、類別月對月變化；右上角「匯出」可下載 CSV / xlsx |
| `/settings/reminders` | 為每筆未付帳單設定提醒：`enabled / days_before / channel`（telegram / ui_banner / both）+ 一鍵測試發送 |
| `/settings/budgets` | 三種 scope 預算（每月總額 / 單類別 / 單銀行）+ 80% / 100% 兩階 Telegram 告警；overview 頁頂部會顯示 active alert banner |
| `/transactions/{id}` | 從交易列表點鉛筆 icon 進入：可改類別（手動覆寫）、備註、標籤、商家別名；手動覆寫後重跑 pipeline 不會被覆蓋 |
| `/settings/rules` | 個人分類規則 CRUD：keyword / exact / regex 三種 pattern + priority + 即時規則測試；regex nested quantifier 警示 banner |

---

## 進階 fallback：檔案與 env 設定

### 各銀行 PDF 密碼

建議使用 `/setup/secrets`。若偏好 env fallback，也可在 `.env` 填 `PDF_PASSWORD_<BANK_CODE>=...`：

| 銀行 | 環境變數 | 取得方式 |
|---|---|---|
| 中國信託 | `PDF_PASSWORD_CTBC` | 個人網銀 → 帳單服務 → PDF 密碼設定 |
| 玉山 | `PDF_PASSWORD_ESUN` | 帳單 PDF 開啟時詢問或網銀設定 |
| 台新 | `PDF_PASSWORD_TAISHIN` | 預設「身分證後 2 碼 + 生日 mmdd」 |
| 聯邦 | `PDF_PASSWORD_UBOT` | 個人網銀設定 |
| 國泰世華 | `PDF_PASSWORD_CATHAY` | 帳單通知信中說明 |
| 永豐 | `PDF_PASSWORD_SINOPAC` | 帳單通知信中說明 |
| 富邦 | `PDF_PASSWORD_FUBON` | 預設身分證號 |

### 啟用 / 停用銀行清單 fallback

`config/banks.yaml`（首次啟動由 image 內建範本自動 seed 至 `${CCAS_CONFIG_LOCATION}`）
預設啟用全部支援銀行。建議使用 `/setup/banks`。若要用 yaml fallback，可編輯該檔案將不需要的銀行 `is_active: false`：

```yaml
banks:
  - bank_code: CTBC
    is_active: true
  - bank_code: SINOPAC
    is_active: false   # 停用
  ...
```

修改後重啟 backend：
```bash
docker compose restart backend
```

### Gmail CLI fallback

建議使用 `/setup/gmail` Web flow。無 GUI 或需要在 host shell 完成授權時，仍可依
[gmail-setup.md](gmail-setup.md) 的 CLI fallback 產生 `token.json`，再放到
`${CCAS_DATA_LOCATION}` 對應目錄。

---

## 進階：自建本機 image

需要本機驗證 production image（例如貢獻者改了 Dockerfile 想驗結果）時：

```bash
docker build --target production -t ghcr.io/<owner>/ccas-backend:local backend/
docker build --target production -t ghcr.io/<owner>/ccas-frontend:local frontend/
docker build -t ghcr.io/<owner>/ccas-proxy:local docker/proxy/

# 切到 prod compose，將 .env 的 CCAS_VERSION 改成 local
sed -i 's/^CCAS_VERSION=.*/CCAS_VERSION=local/' .env
docker compose -f docker-compose.yml up -d
```

---

## 升級到新版

見 [upgrade-guide.md](upgrade-guide.md)。基本上是改 `.env` 的 `CCAS_VERSION` 後
`docker compose pull && up -d`，alembic migration 自動執行。
