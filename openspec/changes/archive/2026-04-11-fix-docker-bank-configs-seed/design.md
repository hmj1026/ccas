## Context

目前兩條部署路徑對 `bank_configs` 表的 seed 行為不一致：

| 路徑 | Seed 方式 | 狀態 |
|---|---|---|
| Host 直跑（`scripts/setup.sh`） | 顯式執行 `uv run python -m ccas.tools.bank_configs --config ../config/banks.yaml --registry ../config/bank-code-registry.yaml --apply` | 可用 |
| Docker compose（`docs/user-guide.md` 主推路徑） | 無任何 seed 步驟；container 也沒 mount `config/` | **破** |

`ccas.tools.bank_configs` 本身只是個 CLI tool，不是問題點；問題在於：

1. Container 看不到 `config/` 目錄（`docker-compose.yaml` 的 volumes 僅含 `./backend/data`、`./scripts`、`./backend/scripts`、`./.env.example`、`./logs`）。
2. `scripts/docker-entrypoint.sh` 的啟動序只有 `check-env.sh` → tesseract 檢查 → `alembic upgrade head` → `exec uvicorn ...`，沒有 seed 銀行設定這一步。
3. `ccas.pipeline.ingestor` 啟動時會呼叫 `get_enabled_bank_configs`，空表直接 raise，使 pipeline 在 Stage 1 當下爆炸。

`openspec/specs/docker-deployment/spec.md` 目前要求 entrypoint 「套用 alembic migration 後啟動 uvicorn」，沒規範 seed 行為 — 這是 spec 的 gap。

## Goals / Non-Goals

**Goals:**
- Docker compose 全新 clone 的機器，`docker compose up` 後第一次 `docker exec ... pipeline --bank CTBC` 就能跑。
- Seed 步驟 idempotent：重啟 container 不重複 CREATE 既有 row；`banks.yaml` 改動後 `docker compose restart backend` 能套用 UPDATE。
- Host 路徑 (`scripts/setup.sh`) 完全不回歸。
- `bank_configs` tool 本身的 argparse 介面維持向後相容。

**Non-Goals:**
- 不改 `banks.yaml` / `bank-code-registry.yaml` 的內容或格式。
- 不動 pipeline ingest 的前置檢查（仍然「表空即報錯」，只是確保空表永不發生）。
- 不做全流程的初始化精靈（不接管 OAuth / Telegram setup 等）。
- 不碰 `scripts/setup.sh`（host 維護者自管）。

## Decisions

### D1：用 volume mount `./config:/config:ro` 而非 COPY 進 image

**選擇**：在 `docker-compose.yaml` 的 backend、worker、scheduler、bot 四個服務各加一行 `- ./config:/config:ro`。

**理由**：
- YAML 設定變更**不需重 build image**，`docker compose restart backend` 即生效 — 對銀行設定這種「文件級」內容更合適。
- 唯讀 mount，container 不會意外污染 host `config/`。
- 與既有 `./scripts:/scripts:ro`、`./backend/scripts:/app/scripts:ro` 風格一致。

**Alternatives considered**：
- (A) 在 `backend/Dockerfile` production stage COPY `config/` 進 image：每次改 yaml 都要 rebuild；與開發節奏不符。
- (B) 用 Docker ConfigMap / Secrets：compose 支援度參差、增加心智負擔。
- (C) 把 yaml 塞進 `backend/data/` 由既有 mount 覆蓋：汙染資料目錄語意，且需改 `scripts/setup.sh` 的路徑假設 — 回歸面積更大。

### D2：環境變數 `BANK_CONFIG_DIR` 覆蓋 CLI 預設路徑

**選擇**：`backend/src/ccas/tools/bank_configs.py` 的 `build_parser` 中，`--config` 與 `--registry` 的 `default` 從常數改為「若 `BANK_CONFIG_DIR` env 存在，使用 `{BANK_CONFIG_DIR}/banks.yaml` / `{BANK_CONFIG_DIR}/bank-code-registry.yaml`；否則維持原本 `../config/...`」。

**理由**：
- Host（`scripts/setup.sh`）與 container（entrypoint）兩條路徑都能用**同一個命令**：`uv run python -m ccas.tools.bank_configs --apply`，只靠環境變數切換路徑。這條原則符合 `.claude/rules/docker-deploy.md` 的 "shared env via x-shared-env anchor"。
- 顯式 flag (`--config / --registry`) 仍可覆蓋，讓 test / debug 情境保持自由度。

**Alternatives considered**：
- (A) 在 entrypoint 內明確寫死 `--config /config/banks.yaml --registry /config/bank-code-registry.yaml`：可行，但兩邊啟動命令就不對稱，未來改 config layout 要改兩處。
- (B) 改 `Settings` 物件增加 `bank_config_dir` 欄位：語意正確但範圍擴張，且本 tool 目前直接用 argparse 不走 Settings，無法就地利用。

### D3：Entrypoint 的 seed 步驟走 idempotent CLI，不做 SQL 探測

**選擇**：`scripts/docker-entrypoint.sh` 於 `alembic upgrade head` 之後新增

```sh
log_info "Seeding bank_configs from /config/..."
uv run python -m ccas.tools.bank_configs --apply || {
  log_error "bank_configs seed failed"
  exit 1
}
```

`bank_configs.py` 的 apply 流程已經是 diff-based（`created / updated / unchanged`），本身就 idempotent，entrypoint 不需要先 SELECT 再決定要不要跑。

**理由**：
- Entrypoint 保持 shell，不注入 Python SQL 探測邏輯。
- Tool 端既有的 unchanged 路徑確保 restart 不做多餘 write。
- Fast-fail：seed 失敗就讓 container 退出，`docker compose` restart policy 會重試；避免在 ingest 時才發現。

**Alternatives considered**：
- (A) Entrypoint 先 `sqlite3 $DB "SELECT count(*) FROM bank_configs"`，非零就 skip：依賴 sqlite CLI 並綁定 DB 格式，不值得。
- (B) Pipeline orchestrator 在 ingest 前自動 seed：混淆職責，且 test fixture 可能就不想 seed。

### D4：Volume mount 作用於哪些服務

**選擇**：backend / worker / scheduler / bot 都 mount。

**理由**：
- Worker 目前不直接讀 yaml，但未來若 RQ job 需要重新驗證銀行設定會讀；先一次到位避免之後補。
- Frontend（nginx）完全不需要，**不**加。
- Redis 不相關，**不**加。

## Risks / Trade-offs

- **[R1] Seed 失敗時 container 無限 restart**：`restart: unless-stopped` 遇上 entrypoint fast-fail 會打迴圈。→ Mitigation：fast-fail 時輸出結構化 error log，hook `/api/health` 由於根本沒啟動 uvicorn 也會顯 unhealthy，使用者能在 `docker compose ps` 立刻看到狀態。

- **[R2] `BANK_CONFIG_DIR` 與 `--config` flag 同時指定時的優先序混淆**：→ Mitigation：argparse 的 `default` 邏輯為「使用者沒給 flag 才讀 env」，文件與 docstring 明述「flag > env > constant」三層優先序，並在 `test_bank_configs_env.py` 各寫一個 case。

- **[R3] `./config:/config:ro` 路徑與既有 host 路徑耦合**：若 user 把 `config/` 改名或移動，entrypoint seed 會失敗。→ Mitigation：compose volume 寫死相對路徑，打破時就直接在 entrypoint 吐錯；`.env.example` / user-guide 都不暴露此路徑給使用者調整。

- **[R4] `banks.yaml` 驗證失敗在啟動時才發現**：改壞 yaml → 重啟 backend → entrypoint 退出 → 服務整掉。→ Mitigation：PR 階段用 `openspec validate` 不會抓，但 `scripts/check-env.sh` 已在 entrypoint 頭段跑，補一段「若 `/config/banks.yaml` 存在則 `yq` dry-run 驗證」即可 — 但這擴大範圍，**延後**至獨立 change 處理（見 Open Questions）。

## Migration Plan

1. 改 code（compose + entrypoint + tool default）。
2. 本機 `docker compose down -v && docker compose up -d backend`，`docker compose logs backend` 確認 seed 行。
3. `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --to ingest` 成功。
4. 無需 DB migration；`bank_configs` 表結構未動。
5. 既有環境升級：只要 `git pull && docker compose up -d --build backend` 即生效。
6. Rollback：revert 三個檔案即可；已 seed 的 `bank_configs` row 無副作用。

## Open Questions

- **OQ1**：是否要在 entrypoint 加「yq dry-run 驗證 `banks.yaml` schema」的防護？目前傾向**不做**，留給獨立 change 處理 config-file hardening。
- **OQ2**：Worker / scheduler 服務的 entrypoint 目前不跑 `docker-entrypoint.sh`（用 compose `command:`），是否需要同步 seed？現行決策：**不需**，因為 worker/scheduler 都依賴 `backend: service_healthy`，backend 的 entrypoint 先跑就夠了。
