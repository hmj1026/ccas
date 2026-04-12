## Why

E2E walkthrough 問題 #3：7 家銀行跑完 `pipeline --from classify --to classify` 後，DB 內 3348 筆 `transactions` **全部** `category = NULL` 或 `未分類`，前端 `/transactions` 與 `/analytics` 圖表完全看不到分類。

根因追查：

1. `sqlite3 backend/data/ccas.db "SELECT COUNT(*) FROM categories;"` 回傳 `0` — **`categories` 表是空的**。
2. `backend/src/ccas/classifier/rules.py` 的 `match` 函數從 DB 載入所有 `categories` row 作為 keyword set；空表直接回傳 `未分類`。
3. `backend/src/ccas/tools/` 目錄下只有 `bank_configs.py`、`gmail_auth.py`，**沒有** `categories.py` 之類的 seed CLI。
4. `config/` 目錄下**沒有** `categories.yaml` 或等價種子檔，也不存在其他 seed 入口。

因此新環境（Docker 或 host）從零啟動時，分類規則恆為空，classifier 形同 no-op。使用者若想讓分類運作必須一筆一筆呼叫 `POST /api/settings/categories`，對 user-guide 流程是破口。

（註：Change #1 `fix-docker-bank-configs-seed` 已處理 bank_configs 類似問題，但 categories 從未有過 seed 機制，屬於全新的 gap，不能併入該 change。）

## What Changes

- **新增 `config/categories.yaml`**：專案層級的預設分類規則清單，涵蓋台灣常見消費分類（餐飲、交通、購物、娛樂、帳單水電、訂閱服務、超商、咖啡、外送、公用事業 等），每類附中英混合 keyword。檔案格式與 `banks.yaml` 風格一致：

  ```yaml
  categories:
    - category: 餐飲
      keywords: [星巴克, 麥當勞, ...]
    - category: 交通
      keywords: [悠遊卡, ...]
  ```

- **新增 `backend/src/ccas/tools/categories.py`**：以 `argparse` 提供 `--apply` / `--dry-run`，讀取 `BANK_CONFIG_DIR` / explicit `--config` 路徑，差分比對 DB 現狀與 YAML 後 UPSERT（與 `bank_configs.py` 相同 idempotent 設計：`created / updated / unchanged` 統計）。優先序：`--config` flag > `BANK_CONFIG_DIR/categories.yaml` env > `../config/categories.yaml` default。

- **修改 `scripts/docker-entrypoint.sh`**：在既有 `bank_configs --apply` 之後新增 `uv run python -m ccas.tools.categories --apply`，fast-fail 同策略。

- **修改 `docker-compose.yaml`**：不需新增 volume mount（`./config:/config:ro` 已由 Change #1 引入，涵蓋 `categories.yaml`）。僅於 `x-shared-env` 維持 `BANK_CONFIG_DIR=/config` 即可。

- **修改 `scripts/setup.sh`**：host 路徑同步新增 `uv run python -m ccas.tools.categories --apply`，與 bank_configs 並排。

- **新增 `backend/tests/integration/tools/test_categories_seed.py`**：TDD 驗證 (1) YAML → DB idempotent apply (2) `BANK_CONFIG_DIR` env 優先序 (3) 衝突規則採最後寫入勝出策略。

- **修改 `docs/user-guide.md`**：在 troubleshooting 新增「分類規則為空時如何重新 seed」；主流程不需使用者手動執行。

**非範圍**：
- 不改 classifier engine 的最長匹配 / id tie-break 邏輯。
- 不改 `categories` table schema。
- 不重跑既有 DB 的 reclassify；使用者若要套用新規則自行跑 `POST /api/bills/{id}/reclassify` 或 pipeline `--from classify`。

## Capabilities

### New Capabilities

- `classification-seed`：新增 capability，涵蓋「預設分類規則的 YAML 來源、CLI seed 工具、docker entrypoint 自動套用、host 與 container 兩條路徑一致的指令介面」。

### Modified Capabilities

- `keyword-mapping-source`：補充「`categories` 表的初始資料來源為 `categories.yaml`，由 `ccas.tools.categories` CLI 於啟動時 idempotent 套用」之需求。
- `docker-deployment`：entrypoint 啟動序補加 `categories` seed 步驟（與 bank_configs 同層）。
- `user-guide`：troubleshooting 章節新增 categories seed 條目。

## Impact

- **程式**：`backend/src/ccas/tools/categories.py`（新檔）、`scripts/docker-entrypoint.sh`、`scripts/setup.sh`、`config/categories.yaml`（新檔）
- **測試**：`backend/tests/integration/tools/test_categories_seed.py`（新檔）
- **文件**：`docs/user-guide.md`
- **相容性**：Category schema 不變；既有既已由 API 新增的 row 與 YAML 不衝突時 `unchanged`，衝突時以 YAML 覆寫（YAML 為 SSOT）。
- **風險**：YAML 內容品質決定分類效果；初版涵蓋常見分類，後續 PR 可逐步擴充。
