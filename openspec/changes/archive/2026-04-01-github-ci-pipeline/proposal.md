## Why

CCAS 目前沒有任何 CI pipeline，程式碼品質完全依賴開發者本地檢查。隨著多個 change 同時進行（parser、auth、bank registry），需要自動化的品質關卡來防止 lint 和型別錯誤進入 develop/master 分支。

## What Changes

- 新增 `.github/workflows/ci.yaml`：GitHub Actions workflow，在 PR 和 push 到 develop/master 時自動執行 backend lint + type check
- 使用 `astral-sh/setup-uv` 安裝 uv，與本地開發一致
- 執行三項檢查：`ruff check`、`ruff format --check`、`pyright`

## Capabilities

### New Capabilities

- `ci-pipeline`: GitHub Actions CI pipeline，自動化後端程式碼品質檢查（lint、format、type check）

### Modified Capabilities

（無）

## Impact

- `.github/workflows/ci.yaml` -- 新增 CI workflow 檔案
- 不影響任何現有程式碼或設定
- 不需要 secrets 或外部服務存取
- CI 執行時間預估 < 2 分鐘（uv sync + lint + pyright）
