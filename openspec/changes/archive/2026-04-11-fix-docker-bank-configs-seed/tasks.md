## 1. TDD 前置

- [x] 1.1 新增 `backend/tests/integration/tools/test_bank_configs_env.py`，以 failing tests 覆蓋 `BANK_CONFIG_DIR` 優先序三個 scenario（env 設定時取 env、flag 覆蓋 env、env 未設時退回 `../config/...`）
- [x] 1.2 執行 `cd backend && uv run pytest tests/integration/tools/test_bank_configs_env.py -x` 確認 RED（未實作前應失敗）

## 2. 修改 bank_configs CLI 讀取路徑

- [x] 2.1 在 `backend/src/ccas/tools/bank_configs.py` 的 `build_parser()` 將 `--config` / `--registry` 的 `default` 改為 dynamic callable：讀取 `BANK_CONFIG_DIR` 環境變數並回傳對應路徑；未設時維持既有 `../config/...`
- [x] 2.2 確保 `argparse` 的優先序：explicit flag > env var > hard-coded default（對應 design D2）
- [x] 2.3 在 module docstring 補一段說明三層優先序
- [x] 2.4 重跑 1.2 的測試，全部 GREEN

## 3. Docker Compose volume mount

- [x] 3.1 在 `docker-compose.yaml` 的 `backend`、`worker`、`scheduler`、`bot` 四個服務 `volumes:` 區塊新增 `- ./config:/config:ro`
- [x] 3.2 在 `x-shared-env` anchor 新增 `BANK_CONFIG_DIR: "/config"` 讓四個服務共享
- [x] 3.3 執行 `docker compose config | grep -A2 bank_config\\|config:/config` 確認渲染後四個服務各自具備 mount 與環境變數

## 4. Entrypoint 自動 seed

- [x] 4.1 在 `scripts/docker-entrypoint.sh` 的 `alembic upgrade head` 之後新增 seed 步驟：`uv run python -m ccas.tools.bank_configs --apply`，fast-fail on 非零退出
- [x] 4.2 Seed 步驟輸出以 `log_info` wrapper 寫入 stdout，失敗用 `log_error`
- [ ] 4.3 `docker compose down -v && docker compose up -d backend`；確認 `docker compose logs backend` 中 seed 步驟回報 `created=7`（首次）或 `unchanged=7`（重啟）
- [ ] 4.4 Smoke：`docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank CTBC --to ingest` 不再報「未找到任何啟用的銀行設定」

## 5. 文件更新

- [x] 5.1 更新 `docs/user-guide.md` 第 6 節「啟動服務」：加一小段「首次啟動時 backend 會自動 seed `bank_configs`，無需手動操作」
- [x] 5.2 在 `docs/user-guide.md` 故障排除章節新增「bank_configs 重新 seed」條目，附 `docker compose restart backend` 與手動 `bank_configs --apply` 兩種做法
- [x] 5.3 檢查 `docs/developer-guide.md` / `docs/deployment-guide.md` 是否有重複或矛盾的 seed 描述，一併同步

## 6. 回歸驗證

- [x] 6.1 全 suite：`cd backend && uv run pytest -x`
- [x] 6.2 Host 路徑未回歸：`cd backend && uv run python -m ccas.tools.bank_configs --apply` 在 host 執行成功（退回 `../config/...`）
- [x] 6.3 在 `docs/e2e-user-guide-walkthrough.md` 問題 #1 狀態改 `archived`，`對應 change slug` 填 `fix-docker-bank-configs-seed`
- [x] 6.4 `openspec validate fix-docker-bank-configs-seed` 通過
