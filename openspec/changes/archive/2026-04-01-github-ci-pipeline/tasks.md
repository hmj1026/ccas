## 1. Workflow 建立

- [x] 1.1 建立 `.github/workflows/ci.yaml`：含 checkout、setup-uv、setup-python、uv sync、ruff check、ruff format --check、pyright 步驟
- [x] 1.2 驗證 YAML 語法正確（`yaml.safe_load`）

## 2. 既有錯誤修正

- [x] 2.1 修正所有 `ruff check` 錯誤（約 69 項）
- [x] 2.2 修正所有 `ruff format` 差異（約 52 檔）
- [x] 2.3 修正所有 `pyright` 型別錯誤（約 7 項）

## 3. 驗證

- [x] 3.1 本地執行三項檢查確認全部通過：`ruff check .` + `ruff format --check .` + `pyright`
- [x] 3.2 確認 `pytest` 在修正後仍全部通過（避免 ruff --fix 引入回歸）
