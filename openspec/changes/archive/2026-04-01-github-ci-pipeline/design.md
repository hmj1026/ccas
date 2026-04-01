## Context

CCAS 目前沒有 CI pipeline。後端使用 Python 3.12 + uv + ruff + pyright，工具鏈已在 `pyproject.toml` 完整定義。分支策略為 `develop` -> `master`（PR-based merge）。

## Goals / Non-Goals

**Goals:**
- 建立最小可用的 GitHub Actions CI workflow
- 在 PR 和 push 到 develop/master 時自動檢查程式碼品質
- 使用與本地開發相同的工具鏈（uv + ruff + pyright）

**Non-Goals:**
- 不包含測試執行（pytest）-- 可在後續 change 加入
- 不包含前端檢查 -- 可在後續 change 加入
- 不包含部署或 release 流程
- 不設定 branch protection rules（需 repo admin 手動設定）

## Decisions

### D1: 單一 workflow 檔案，單一 job

所有三項檢查（ruff check、ruff format --check、pyright）放在同一個 job 的連續 steps 中。

**Why:** 三項檢查都快速（< 30 秒），且共用相同的依賴安裝。分成多個 job 反而增加 runner 啟動開銷。

**Alternatives considered:**
- 多個平行 jobs：增加複雜度，對小型檢查無效益
- 使用 matrix strategy：不需要，只有一個 Python 版本

### D2: 使用 astral-sh/setup-uv 官方 Action

**Why:** uv 是本專案的 package manager，`astral-sh/setup-uv` 是 Astral 官方維護的 GitHub Action，自動處理 uv 安裝與快取。

**Alternatives considered:**
- pip install uv：無快取，較慢
- 預裝 uv 的 Docker image：增加維護成本

### D3: 所有命令在 backend/ 目錄執行

使用 `defaults.run.working-directory: backend` 設定 job 層級的工作目錄。

**Why:** 後端程式碼和 `pyproject.toml` 都在 `backend/` 子目錄。避免每個 step 重複 `cd backend`。

### D4: 不需要 secrets 或環境變數

lint 和 type check 不需要資料庫、API token 或外部服務存取。所有檢查都是純靜態分析。

## Risks / Trade-offs

- **[既有 lint 錯誤]** 目前 codebase 有約 69 個 ruff 錯誤和 7 個 pyright 錯誤。首次 push 到 develop 後 CI 會失敗。Mitigation: 在合併此 change 前先修正既有錯誤，或分階段引入（先只加 pyright，再加 ruff）。
- **[GitHub Actions 配額]** 公開 repo 免費，私有 repo 有 2,000 分鐘/月限制。Mitigation: 此 workflow 預估每次 < 2 分鐘，即使每天 10 次觸發也僅消耗約 600 分鐘/月。
