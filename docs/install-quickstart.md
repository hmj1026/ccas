# CCAS 快速安裝（Docker Compose / pull-only）

本文件針對「想在本機快速跑起 CCAS 帳單自動化、不打算自行 build」的使用者；只需要下載
`docker-compose.yml` + `example.env` 兩個檔案即可啟動。

> **本路徑為兩種啟動方式之一**：
> - **dev（含原始碼）**：見 [docs/developer-guide.md](developer-guide.md)，根目錄 `docker-compose.yaml` + override
> - **prod（pull-only）**：本文，`docker/docker-compose.yml` 純 image
>
> **prod self-build 中間路徑（在根目錄 compose 上 `--target production`）已棄用**。如需本機驗證 production image，請改用 `CCAS_VERSION=local` 搭配 prod compose（見「進階：自建本機 image」段落）。

---

## 步驟 0：完成 Gmail OAuth 前置設定（必做）

CCAS 需要從你的 Gmail 收取信用卡帳單 PDF。在啟動 Docker 之前，**必須**先取得 Google
OAuth `credentials.json`：

完整步驟見 [docs/gmail-setup.md](gmail-setup.md)（建立 GCP project → 啟用 Gmail API →
設定 OAuth consent screen → 下載 credentials.json）。

> 終端使用者的 Web UI 化（瀏覽器內完成 OAuth）規劃在下一個 change `oauth-onboarding-ui`，
> 屆時可省略本步驟並改用 `/setup/gmail` 頁面。當前版本仍需手動。

## 步驟 1：建立工作目錄

```bash
mkdir ~/ccas && cd ~/ccas
```

## 步驟 2：下載 release artifacts

從 [GitHub Releases](https://github.com/<owner>/ccas/releases/latest) 下載最新版的
`docker-compose.yml` 與 `example.env`：

```bash
RELEASE=v0.1.0   # 改為要安裝的精確版號
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

**選填但常見**：

- `PDF_PASSWORD_<BANK_CODE>`：各銀行 PDF 密碼（多家銀行各自填）
- `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`：填妥則 bot 自動啟用，不需 `--profile`

> `API_TOKEN` **可不填**：entrypoint 首啟會自動產生 32-byte token 並落地至
> `${CCAS_DATA_LOCATION}/secrets/api-token`（檔案權限 0600）。若顯式設為空字串會被驗證腳本擋下。

## 步驟 4：放置 Gmail credentials

```bash
mkdir -p ./data
cp /path/to/credentials.json ./data/credentials.json
```

`./data` 對應 `.env` 的 `CCAS_DATA_LOCATION` 預設值；改路徑時兩邊同步。

## 步驟 5：啟動

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

## 步驟 6：首次登入

CCAS 採「API token 即 Web UI 登入憑證」設計（首次部署不需要使用者帳號註冊）：

```bash
# 1) 取得自動產生的 token
cat ./data/secrets/api-token   # CCAS_DATA_LOCATION 對應路徑

# 2) 開啟瀏覽器
#    http://localhost:8080/login

# 3) 將上一步的 token 貼到輸入框送出
#    成功後即進入 dashboard
```

> 之後想換 token？目前需手動覆寫 `./data/secrets/api-token` 並重啟 backend
> （`docker compose restart backend`）。下一個 change `oauth-onboarding-ui` 將提供
> `/setup/admin` 頁面內的 rotate UI。

---

## 目前仍需手動設定的項目

本版（`compose-pull-deploy`）尚未涵蓋 onboarding Web UI；以下設定仍需手動編輯，待
下一個 change `oauth-onboarding-ui` 落地後可改在 `/setup/*` 頁面內完成：

### 各銀行 PDF 密碼

每家銀行的帳單 PDF 都有自己的解密密碼規則（多為身分證後 N 碼 + 生日 / 自設密碼），
需填入 `.env` 的 `PDF_PASSWORD_<BANK_CODE>=...`：

| 銀行 | 環境變數 | 取得方式 |
|---|---|---|
| 中國信託 | `PDF_PASSWORD_CTBC` | 個人網銀 → 帳單服務 → PDF 密碼設定 |
| 玉山 | `PDF_PASSWORD_ESUN` | 帳單 PDF 開啟時詢問或網銀設定 |
| 台新 | `PDF_PASSWORD_TAISHIN` | 預設「身分證後 2 碼 + 生日 mmdd」 |
| 聯邦 | `PDF_PASSWORD_UBOT` | 個人網銀設定 |
| 國泰世華 | `PDF_PASSWORD_CATHAY` | 帳單通知信中說明 |
| 永豐 | `PDF_PASSWORD_SINOPAC` | 帳單通知信中說明 |
| 富邦 | `PDF_PASSWORD_FUBON` | 預設身分證號 |

### 啟用 / 停用銀行清單

`config/banks.yaml`（首次啟動由 image 內建範本自動 seed 至 `${CCAS_CONFIG_LOCATION}`）
預設啟用全部支援銀行。若你只用其中幾家，請編輯該檔案將不需要的銀行 `is_active: false`：

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

> 下一個 change `oauth-onboarding-ui` 將提供 `/setup/banks` 頁面取代手動編輯。

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
