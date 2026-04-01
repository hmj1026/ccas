## ADDED Requirements

### Requirement: CI workflow 在指定事件觸發時自動執行後端程式碼品質檢查

系統 SHALL 提供 GitHub Actions workflow，在 push 到 `develop`/`master` 分支或針對這兩個分支建立 PR 時，自動執行後端 lint 與 type check。

#### Scenario: Push 到 develop 分支觸發 CI

- **WHEN** 開發者 push 程式碼到 `develop` 分支
- **THEN** GitHub Actions SHALL 自動執行後端 lint + type check workflow

#### Scenario: PR 到 master 分支觸發 CI

- **WHEN** 開發者建立或更新以 `master` 為目標的 PR
- **THEN** GitHub Actions SHALL 自動執行後端 lint + type check workflow

#### Scenario: Push 到 feature 分支不觸發 CI

- **WHEN** 開發者 push 到非 `develop`/`master` 的分支（如 `feature/xxx`）
- **THEN** CI workflow SHALL NOT 被觸發

### Requirement: CI 執行 ruff lint 檢查

workflow SHALL 執行 `ruff check .` 對後端程式碼進行 lint 檢查，使用 `pyproject.toml` 中已定義的規則。

#### Scenario: Lint 通過

- **WHEN** 後端程式碼無 ruff 違規
- **THEN** ruff check step SHALL 回傳 exit code 0

#### Scenario: Lint 失敗

- **WHEN** 後端程式碼存在 ruff 違規
- **THEN** ruff check step SHALL 回傳非零 exit code，workflow 標記為失敗

### Requirement: CI 執行 ruff format 格式驗證

workflow SHALL 執行 `ruff format --check .` 驗證後端程式碼格式，不自動修改檔案。

#### Scenario: 格式一致

- **WHEN** 所有後端檔案已正確格式化
- **THEN** ruff format check step SHALL 回傳 exit code 0

#### Scenario: 格式不一致

- **WHEN** 有後端檔案未正確格式化
- **THEN** ruff format check step SHALL 回傳非零 exit code，workflow 標記為失敗

### Requirement: CI 執行 pyright 型別檢查

workflow SHALL 執行 `pyright` 對後端程式碼進行靜態型別檢查，使用 `pyproject.toml` 中已定義的設定。

#### Scenario: 型別檢查通過

- **WHEN** 後端程式碼無型別錯誤
- **THEN** pyright step SHALL 回傳 exit code 0

#### Scenario: 型別檢查失敗

- **WHEN** 後端程式碼存在型別錯誤
- **THEN** pyright step SHALL 回傳非零 exit code，workflow 標記為失敗

### Requirement: CI 使用 uv 管理 Python 依賴

workflow SHALL 使用 `uv sync` 安裝所有依賴（含 dev dependencies），確保 CI 環境與本地開發一致。

#### Scenario: 依賴安裝成功

- **WHEN** CI workflow 開始執行
- **THEN** SHALL 使用 `uv sync` 安裝依賴，且後續 lint/type check 步驟可正常使用 `uv run`
