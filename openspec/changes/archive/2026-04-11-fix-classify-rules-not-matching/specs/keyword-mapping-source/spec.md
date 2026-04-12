## MODIFIED Requirements

### Requirement: 從 `categories` 資料表載入分類規則

系統 SHALL 從 `categories` 資料表讀取所有關鍵字與對應分類，作為 keyword classifier 的規則來源。`categories` 表的**初始基線資料 SHALL 由 `config/categories.yaml` 透過 `ccas.tools.categories` CLI 於部署時 idempotent 套用**；API 層（`/api/settings/categories`）負責使用者個人化擴充。

#### Scenario: 載入所有分類映射

- **WHEN** 分類引擎初始化或重新載入規則
- **THEN** 系統會讀取 `categories` 資料表中的所有 `keyword` 與 `category` 組合

#### Scenario: 規則異動影響後續分類

- **WHEN** `categories` 資料表中的關鍵字映射被新增、修改或刪除
- **THEN** 後續分類執行會以更新後的資料表內容為準

#### Scenario: 新環境初始規則來源為 YAML seed

- **WHEN** 全新 clone 的部署執行 `scripts/setup.sh` 或 `docker compose up -d backend`
- **THEN** `categories` 表 SHALL 在 classifier 首次執行前已被 `ccas.tools.categories --apply` 填入 YAML 中定義的預設規則
