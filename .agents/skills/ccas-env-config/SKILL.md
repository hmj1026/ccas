---
name: ccas-env-config
description: "CCAS 專案環境變數與設定檔載入邏輯。使用時機：處理 .env、新增/修改環境變數、Vite proxy 設定、Docker env_file 注入、pydantic-settings 載入路徑問題、或需要向使用者解釋環境設定結構時。"
---

# CCAS 環境設定

## 核心原則：單一 `.env`，專案根目錄共用

專案根目錄有**唯一一份** `.env`，backend 與 frontend 共用。

| 消費者 | 載入方式 |
|---|---|
| Backend | `pydantic-settings` 從 `backend/` 工作目錄載入 `../.env`（相對路徑） |
| Frontend | Vite dev server 將 `/api` 代理到 `http://127.0.0.1:8000`（設定在 `vite.config.ts`）；**開發環境不需要 `VITE_API_BASE`** |
| Docker | `docker-compose.yaml` 透過 `env_file: ./.env` 注入 |
| 範本 | `.env.example` 文件化所有可用變數 |

## 驗證與除錯

```bash
./scripts/check-env.sh    # 檢查 .env 缺漏變數
```

## 常見變數分類

- **API 認證**：`API_TOKEN`
- **Telegram**：`TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`TELEGRAM_ALLOWED_CHAT_IDS`
- **Gmail**：`GMAIL_CREDENTIALS_PATH`、`GMAIL_TOKEN_PATH`
- **Storage**：`STAGING_DIR`
- **Database**：`DATABASE_URL`（Docker override 使用 `/data/` 前綴）
- **Redis**：`REDIS_URL`

## Docker 環境覆寫

- 共用環境變數透過 `docker-compose.yaml` 的 `x-shared-env` YAML anchor 設定
- Docker 特有的覆寫（例如 `DATABASE_URL` 改為 `/data/` 前綴）放在 `x-shared-env` 內
- 本地預設路徑在 `.env.example` 使用相對路徑（`./data/...`）

## 安全原則

- **不可硬編碼** secrets、tokens、passwords 於 Dockerfile 或 compose 檔
- `.env` 不進版控（`.gitignore` 已排除）
- Gitleaks 規則於 `.gitleaks.toml` 掃描 secrets
