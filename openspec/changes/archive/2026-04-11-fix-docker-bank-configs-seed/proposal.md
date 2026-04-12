## Why

依 `docs/user-guide.md` 第 5~7 節走 docker compose 流程時，首次 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC` 會直接失敗並回報：

```
[Ingest] 未找到任何啟用的銀行設定。請先執行 python -m ccas.tools.bank_configs --apply 初始化銀行設定。
```

根因有二：

1. **Container 未 mount `config/`**：`docker-compose.yaml` 只 mount `./backend/data:/data`、`./scripts:/scripts:ro`、`./backend/scripts:/app/scripts:ro`，專案根目錄 `config/` 並未暴露給 container。
2. **Entrypoint 不做 seed**：`scripts/docker-entrypoint.sh` 只跑 `alembic upgrade head`，沒有類似 `bank_configs --apply` 的初始化步驟。`bank_configs` 表留空，pipeline ingest 前置檢查就直接拒跑。

後果：使用者嚴格按照 user-guide 走，在 Stage 1 就撞牆，必須離開 user-guide 去翻 `scripts/setup.sh`（host 專用）才能解。這條流程目前**不可重現**，本次 E2E 走查 (`docs/e2e-user-guide-walkthrough.md` 問題 #1) 只能用 workaround（手動把 yaml 複製到 `backend/data/` 再指定路徑執行）繞過。

## What Changes

- **修改 `docker-compose.yaml`**：為 backend / worker / scheduler / bot 四個會 seed 或讀設定的服務新增 `- ./config:/config:ro` volume mount（唯讀）。
- **修改 `scripts/docker-entrypoint.sh`**：在 `alembic upgrade head` 之後、`exec` 啟動 uvicorn 之前，新增「若 `bank_configs` 表為空則執行 `python -m ccas.tools.bank_configs --config /config/banks.yaml --registry /config/bank-code-registry.yaml --apply`」的 idempotent 步驟。空表檢查可用 SQL 或 dry-run exit code 判斷。
- **修改 `backend/src/ccas/tools/bank_configs.py`**：保留現行 `../config/...` 預設值（host 執行相容），但改為**若環境變數 `BANK_CONFIG_DIR` 存在則優先採用該目錄**；docker-compose 的 shared env 注入 `BANK_CONFIG_DIR=/config`。這樣 host 與 container 兩種執行路徑都不需改 flag。
- **修改 `docs/user-guide.md` 第 6~7 節**：加一行「首次 `docker compose up` 時 backend container 會自動 seed 銀行設定，無需額外指令」，並在 troubleshooting 新增「若 `bank_configs` 為空時如何手動重跑 entrypoint seed 步驟」。

**非範圍**：
- 不動 `scripts/setup.sh`（host 路徑維持原樣）
- 不改 `banks.yaml` / `bank-code-registry.yaml` 內容
- 不改 pipeline ingest 的前置檢查行為（仍然「表空即報錯」，僅讓空表永不發生）

## Capabilities

### New Capabilities

無。本變更屬於既有部署流程的修補，不引入新 capability。

### Modified Capabilities

- `docker-deployment`: 新增需求「backend container 啟動時必須先確保 `bank_configs` 表已 seed；seed 需 idempotent，來源為 container 內唯讀 mount 的 `/config/banks.yaml` + `/config/bank-code-registry.yaml`」。
- `user-guide`: 文件更新以反映 seed 由 entrypoint 自動化，從 pre-flight 操作步驟中移除「手動 seed bank_configs」的暗示。

## Impact

- **程式**：`docker-compose.yaml`、`scripts/docker-entrypoint.sh`、`backend/src/ccas/tools/bank_configs.py`
- **文件**：`docs/user-guide.md`
- **測試**：需新增 `backend/tests/integration/tools/test_bank_configs_env.py`（驗證 `BANK_CONFIG_DIR` 環境變數優先於 flag 預設值）；entrypoint 行為則透過 docker integration smoke（在 CI 最小 compose up 後檢查 `bank_configs` row 數 > 0）。
- **相容性**：Host 直接跑 `scripts/setup.sh` 的流程不受影響（`BANK_CONFIG_DIR` 未設時回退到 `../config/...` 預設值）。
- **風險**：entrypoint seed 若失敗應 fast-fail 不啟動 uvicorn，避免 pipeline 啟動後才在 ingest 階段崩掉；與 `check-env.sh` 同層處理。
