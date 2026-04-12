# docker-deployment Specification

## Purpose
TBD - created by archiving change docker-production-deploy. Update Purpose after archive.
## Requirements
### Requirement: Production Docker Compose configuration

The system SHALL provide a `docker-compose.yaml` that serves as the production configuration, using the `production` target for both backend and frontend services.

#### Scenario: Production mode startup

- **WHEN** an operator runs `docker compose -f docker-compose.yaml up`
- **THEN** the frontend SHALL serve static files via nginx on port 80, the backend SHALL run uvicorn on port 8000, and all services SHALL start with `restart: unless-stopped`

#### Scenario: Frontend serves API requests via reverse proxy

- **WHEN** a browser requests `/api/*` from the frontend origin
- **THEN** nginx SHALL proxy the request to `http://backend:8000` with proper forwarding headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`)

#### Scenario: Frontend serves SPA routes

- **WHEN** a browser requests any non-API, non-asset path
- **THEN** nginx SHALL fall back to `index.html` for client-side routing

### Requirement: RQ Worker 服務定義

系統 SHALL 在 `docker-compose.yaml` 定義一個 `worker` 服務，負責消費 Redis Queue 中的 pipeline 任務。Worker 服務 SHALL 使用與 backend 相同的 build context 與 production target，共用相同的 volumes、env_file 與 shared environment。

#### Scenario: Worker 服務存在於 Docker Compose 配置

- **WHEN** 執行 `docker compose config`
- **THEN** 輸出 SHALL 包含名為 `worker` 的服務定義

#### Scenario: Worker 在 backend 就緒後啟動

- **WHEN** `docker compose up` 啟動所有服務
- **THEN** `worker` 服務 SHALL 等待 `backend`（service_healthy）與 `redis`（service_healthy）就緒後才啟動

#### Scenario: Worker 消費佇列中的 pipeline 任務

- **WHEN** `/api/pipeline/trigger` 端點將任務排入 Redis Queue
- **THEN** `worker` 服務 SHALL 從佇列取出並執行 `run_pipeline_sync`，任務不會無限期滯留在 Redis 中

#### Scenario: Worker 異常終止後自動重啟

- **WHEN** `worker` 服務非預期終止
- **THEN** Docker Compose SHALL 依 `restart: unless-stopped` 策略自動重啟 worker

### Requirement: Credential file mounting

The system SHALL support mounting Gmail OAuth credentials from the host into backend containers via bind mounts.

#### Scenario: Credentials available in container

- **WHEN** `docker-compose.yaml` includes bind mounts for `./credentials/credentials.json` and `./credentials/token.json`
- **THEN** the backend container SHALL have these files accessible at `/data/credentials.json` (read-only) and `/data/token.json` (writable)

#### Scenario: Credentials directory gitignored

- **WHEN** a developer checks `.gitignore`
- **THEN** the `credentials/` directory SHALL be listed to prevent accidental commits

### Requirement: OCR available in all Docker environments

The system SHALL install `tesseract-ocr` and `tesseract-ocr-chi-tra` in both the `dev` and `production` stages of `backend/Dockerfile`.

#### Scenario: OCR works in dev Docker

- **WHEN** the backend runs from the `dev` Docker target
- **THEN** `is_ocr_available()` SHALL return `True`

#### Scenario: OCR works in production Docker

- **WHEN** the backend runs from the `production` Docker target
- **THEN** `is_ocr_available()` SHALL return `True`

### Requirement: OCR availability logged at startup

The system SHALL log the tesseract OCR availability status during container startup, before the application begins serving requests.

#### Scenario: Tesseract available

- **WHEN** the container starts and `tesseract` is found in PATH
- **THEN** the startup log SHALL include an INFO-level message indicating OCR is available

#### Scenario: Tesseract not available

- **WHEN** the container starts and `tesseract` is not found in PATH
- **THEN** the startup log SHALL include a WARNING-level message indicating OCR is unavailable with installation hints

### Requirement: Production deployment documentation

The system SHALL provide a `docs/deployment-guide.md` covering prerequisites, credential setup, environment configuration, first launch, health verification, and backup strategy.

#### Scenario: Operator follows deployment guide

- **WHEN** an operator follows `docs/deployment-guide.md` on a fresh server with Docker installed
- **THEN** all 5 services (backend, scheduler, bot, frontend, redis) SHALL start successfully and pass health checks

### Requirement: Logs bind mount for persistence

Docker Compose SHALL 使用 bind mount 將專案根目錄 `./logs/` 掛載至容器內 `/logs`，搭配 `logs/.gitkeep` 確保目錄存在於 git。

#### Scenario: container restart preserves logs
- **WHEN** 任一服務容器重啟
- **THEN** 先前的日誌檔案仍保留在 host 的 `./logs/` 目錄中

#### Scenario: all services mount logs directory
- **WHEN** docker-compose up 啟動所有服務
- **THEN** backend、worker、scheduler、bot 均掛載 `./logs:/logs`

#### Scenario: services use independent log file prefixes
- **WHEN** 多個服務同時寫入 `/logs` 目錄
- **THEN** 各服務透過 `LOG_FILE_PREFIX` 環境變數寫入獨立檔案（`ccas-backend.log`、`ccas-worker.log`、`ccas-scheduler.log`、`ccas-bot.log`）

### Requirement: LOG_DIR in shared environment

系統 SHALL 在 `x-shared-env` anchor 中加入 `LOG_DIR` 設定。

#### Scenario: shared-env includes LOG_DIR
- **WHEN** 服務使用 `<<: *shared-env`
- **THEN** `LOG_DIR` 被設定為 `/logs`

### Requirement: Bank config volume mount

The system SHALL mount the host `./config/` directory into backend, worker, scheduler, and bot containers as read-only at `/config`, so that `banks.yaml` and `bank-code-registry.yaml` are available inside the container without rebuilding the image.

#### Scenario: Backend container can read bank config

- **WHEN** `docker compose up -d backend` completes
- **THEN** `docker exec ccas-backend-1 ls /config/banks.yaml /config/bank-code-registry.yaml` SHALL return both files with exit code 0

#### Scenario: Config mount is read-only

- **WHEN** the backend container attempts to write to `/config/banks.yaml`
- **THEN** the write SHALL fail with a read-only filesystem error

#### Scenario: All pipeline-relevant services receive the mount

- **WHEN** `docker compose config` is rendered
- **THEN** the `backend`, `worker`, `scheduler`, and `bot` services SHALL each include `./config:/config:ro` in their `volumes`; the `frontend` and `redis` services SHALL NOT include it

### Requirement: Automatic bank_configs seeding on backend startup

The system SHALL seed the `bank_configs` table from `/config/banks.yaml` and `/config/bank-code-registry.yaml` during backend container startup, after database migrations have been applied and before uvicorn starts serving requests. The seed step MUST be idempotent — unchanged rows SHALL NOT be rewritten on subsequent restarts.

#### Scenario: Fresh container seeds from empty table

- **WHEN** a clean `docker compose up -d backend` runs against an empty database
- **THEN** the entrypoint SHALL execute `uv run python -m ccas.tools.bank_configs --apply`, the tool SHALL report `created=N` where N matches the number of enabled banks in `banks.yaml`, and uvicorn SHALL start successfully afterwards

#### Scenario: Restart after seed is idempotent

- **WHEN** a backend container that has already seeded `bank_configs` is restarted without changing `banks.yaml`
- **THEN** the entrypoint seed step SHALL report `created=0 updated=0 unchanged=N` and SHALL NOT raise

#### Scenario: Seed failure aborts startup

- **WHEN** the bank_configs seed step exits with a non-zero status (e.g. malformed YAML, DB unreachable)
- **THEN** `docker-entrypoint.sh` SHALL exit non-zero without `exec`-ing uvicorn, and the container SHALL be marked unhealthy by Compose

#### Scenario: Pipeline ingest succeeds immediately after first startup

- **WHEN** an operator runs `docker compose up -d` on a fresh clone followed by `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --to ingest`
- **THEN** the pipeline SHALL NOT raise `未找到任何啟用的銀行設定` and the ingest stage SHALL proceed past bank-config validation

### Requirement: BANK_CONFIG_DIR environment variable overrides CLI defaults

The `ccas.tools.bank_configs` CLI SHALL honor the `BANK_CONFIG_DIR` environment variable as the source of default paths for `--config` and `--registry`. Explicit `--config` / `--registry` flags MUST still take precedence over the environment variable, and the environment variable MUST take precedence over the hard-coded `../config/...` defaults.

#### Scenario: Env var sets defaults inside container

- **WHEN** `BANK_CONFIG_DIR=/config` is set and `uv run python -m ccas.tools.bank_configs --apply` is invoked with no path flags
- **THEN** the tool SHALL read `/config/banks.yaml` and `/config/bank-code-registry.yaml`

#### Scenario: Explicit flag overrides env var

- **WHEN** `BANK_CONFIG_DIR=/config` is set and the tool is invoked as `--config /tmp/custom-banks.yaml --registry /tmp/custom-registry.yaml --apply`
- **THEN** the tool SHALL read from the `/tmp/custom-*` paths and ignore `BANK_CONFIG_DIR`

#### Scenario: Host fallback when env var unset

- **WHEN** `BANK_CONFIG_DIR` is unset (as in `scripts/setup.sh` host flow)
- **THEN** the tool SHALL fall back to the hard-coded `../config/banks.yaml` and `../config/bank-code-registry.yaml` defaults relative to the backend working directory

### Requirement: Automatic categories seeding on backend startup

The system SHALL seed the `categories` table from `/config/categories.yaml` during backend container startup, immediately after the `bank_configs` seed step and before uvicorn starts serving requests. The seed step MUST be idempotent and MUST fast-fail with non-zero exit on failure.

#### Scenario: Fresh container seeds categories

- **WHEN** a clean `docker compose up -d backend` runs against an empty database
- **THEN** the entrypoint SHALL execute `uv run python -m ccas.tools.categories --apply` after `bank_configs --apply`, the tool SHALL report `created=N` matching the YAML row count, and uvicorn SHALL start successfully afterwards

#### Scenario: Restart is idempotent

- **WHEN** a backend container that has already seeded categories is restarted without changing `categories.yaml`
- **THEN** the entrypoint categories step SHALL report `created=0 updated=0 unchanged=N` and SHALL NOT raise

#### Scenario: Seed failure aborts startup

- **WHEN** the categories seed step exits with non-zero status
- **THEN** `docker-entrypoint.sh` SHALL exit non-zero without `exec`-ing uvicorn

### Requirement: Docker image SHALL 預載 EasyOCR 模型權重

Backend Docker image build 階段 SHALL 預下載 EasyOCR 英文模型權重（`craft_mlt_25k.pth` + `english_g2.pth`），避免容器 runtime 首次呼叫 FUBON fetcher 時才觸發下載（會拖長啟動時間且依賴 runtime 對外網路）。

#### Scenario: image 內包含 EasyOCR 權重檔

- **WHEN** backend image build 完成後檢查 `/root/.EasyOCR/model/` 或對應使用者家目錄
- **THEN** 目錄 SHALL 存在 `craft_mlt_25k.pth` 與 `english_g2.pth` 兩個檔案

#### Scenario: 容器啟動後第一次呼叫不觸發下載

- **WHEN** 容器 fresh 啟動後首次執行 FUBON fetcher，且 runtime 無對外網路存取
- **THEN** EasyOCR `Reader(['en'])` SHALL 成功初始化，不拋出下載相關錯誤

### Requirement: Docker Compose SHALL 將 FUBON 專屬 env 視為可選

`docker-compose.yml` 與 `x-shared-env` anchor SHALL 將 `FUBON_ID_NUMBER`、`FUBON_BIRTHDAY`、`FUBON_CAPTCHA_MAX_RETRIES`、`FUBON_CAPTCHA_FALLBACK_LLM` 列入 env 傳遞清單但不 hardcode 值；未設定時容器 SHALL 正常啟動，FUBON fetcher 會在執行時回 `credentials_missing` 的明確錯誤。

#### Scenario: 未設 FUBON env 的 compose up

- **WHEN** 使用者 `.env` 完全沒有 `FUBON_*` 變數，執行 `docker compose up -d`
- **THEN** 所有 7 個 services SHALL 正常 healthy，backend SHALL 正常提供其他銀行的 pipeline

