## ADDED Requirements

### Requirement: Categories YAML 作為預設分類規則 SSOT

The system SHALL provide a `config/categories.yaml` file as the single source of truth for default keyword→category classification rules. The file SHALL list categories with nested keyword arrays and be consumed by a dedicated seed CLI to populate the `categories` database table.

#### Scenario: YAML 結構

- **WHEN** `config/categories.yaml` 被讀取
- **THEN** 檔案 SHALL 包含頂層 `categories:` list，每個 item 具有 `category: <str>` 與 `keywords: [<str>, ...]` 兩個必要欄位

#### Scenario: 至少涵蓋 8 類

- **WHEN** 初版 `categories.yaml` 被 commit
- **THEN** 檔案 SHALL 至少包含「餐飲、交通、購物、娛樂、帳單水電、訂閱服務、超商、咖啡」8 個 category 的 keyword list

### Requirement: ccas.tools.categories CLI 提供 idempotent seed

The system SHALL provide `python -m ccas.tools.categories` CLI that loads `categories.yaml` and applies it to the `categories` table via diff-based UPSERT, reporting `created / updated / unchanged` counts. The CLI MUST be idempotent across repeated invocations.

#### Scenario: 空表首次 apply

- **WHEN** `categories` 表為空且執行 `uv run python -m ccas.tools.categories --apply`
- **THEN** CLI SHALL insert 所有 YAML 中的 `(keyword, category)` row，輸出 `created=N unchanged=0 updated=0`，exit code 0

#### Scenario: 重複 apply 不重寫

- **WHEN** `categories` 表已完整 seed 過且 YAML 未變
- **THEN** 再次 `--apply` SHALL 輸出 `created=0 updated=0 unchanged=N`，exit code 0，且不產生任何 SQL write

#### Scenario: YAML 更新單一 keyword 的分類

- **WHEN** YAML 將「麥當勞」從「餐飲」改為「外食」後再 apply
- **THEN** CLI SHALL 對該 row 發出 UPDATE，輸出含 `updated=1`

#### Scenario: 使用者自訂 row 被保留

- **GIVEN** `categories` 表含一筆透過 API 新增但不在 YAML 的 row `(keyword="我的咖啡店", category="餐飲")`
- **WHEN** CLI `--apply` 執行
- **THEN** 該 row SHALL 保留不動，`unchanged` / `updated` / `created` 計數皆不含它

#### Scenario: BANK_CONFIG_DIR 環境變數套用

- **WHEN** `BANK_CONFIG_DIR=/config` 設定且執行 `--apply` 未指定 `--config` 時
- **THEN** CLI SHALL 讀取 `/config/categories.yaml`

#### Scenario: 顯式 flag 覆蓋 env

- **WHEN** `BANK_CONFIG_DIR=/config` 設定但以 `--config /tmp/custom.yaml --apply` 呼叫
- **THEN** CLI SHALL 讀取 `/tmp/custom.yaml` 並忽略 env

#### Scenario: Host fallback

- **WHEN** `BANK_CONFIG_DIR` 未設定（host 執行情境）
- **THEN** CLI SHALL fall back 至 `../config/categories.yaml` 預設路徑（相對於 backend 工作目錄）

#### Scenario: Dry-run 不寫 DB

- **WHEN** 執行 `--dry-run`
- **THEN** CLI SHALL 輸出 diff summary 但 SHALL NOT 發出任何 SQL write
