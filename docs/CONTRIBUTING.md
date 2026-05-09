# 貢獻指南

## 前置閱讀

開始貢獻前請先閱讀：

- [開發者指南](developer-guide.md) — 環境設定、架構總覽、測試流程
- [CLAUDE.md](../CLAUDE.md) — 專案 SSOT：技術棧、指令、OpenSpec 工作流

## 分支策略

| 分支 | 用途 |
|------|------|
| `master` | 穩定版本，只接受 PR merge |
| `develop` | 開發主線，feature / fix branches 的目標 |
| `feat/<name>` | 新功能 |
| `fix/<name>` | Bug 修正 |

從 `develop` 建立 branch，PR 目標也是 `develop`。

## Commit Message 格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
<type>: <description>

<optional body>
```

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修正 |
| `refactor` | 重構（不改行為）|
| `docs` | 文件 |
| `test` | 測試 |
| `chore` | 工具、設定 |
| `perf` | 效能改善 |
| `ci` | CI/CD |

範例：
```
feat: add CTBC parser ROC format support
fix: correct date parsing for December billing
refactor: extract pipeline stage validation
docs: update developer guide
test: add stage control unit tests
```

## PR 流程

1. 從 `develop` 建立 feature / fix branch
2. 實作功能，先寫測試（TDD）
3. 執行品質檢查（見下方）
4. 推送並在 GitHub 建立 PR，目標 branch：`develop`
5. PR 說明填寫變更摘要與測試計畫

## Git Hooks 設定

### Claude Code 使用者（自動）

使用 Claude Code 開發時，**無需手動安裝任何 hook**。  
Session 結束時，若有檔案異動，`.claude/hooks/ccas-pre-push-stop.sh` 會自動執行 `scripts/pre-push.sh`，在 session 關閉前完成完整品質檢查。此機制不依賴 git，Claude 若發現問題仍可在同一 session 內修正。

### 非 Claude 工作流（手動 git push）

若直接使用 `git push` 而非透過 Claude Code，建議安裝 git hooks：

```bash
./scripts/setup-hooks.sh
```

### Pre-commit hook（`scripts/pre-commit.sh`）

只針對 **staged 檔案**執行，速度快：

| 步驟 | 說明 |
|------|------|
| gitleaks secret scan | 掃描 staged diff 是否含金鑰/PII（需安裝 `brew install gitleaks`；未安裝時警告不中止）|
| ruff check --fix | 自動修正 lint 問題後重新 stage |
| ruff format | 格式化 Python 檔案 |
| pyright | 型別檢查（針對整個 backend）|
| eslint | 針對 staged `.ts`/`.tsx` 檔案 |

### Pre-push hook（`scripts/pre-push.sh`）

模擬完整 CI，執行完整驗證。觸發方式有兩種：

| 觸發 | 條件 |
|------|------|
| Claude Code Stop hook（自動） | Session 結束且有檔案異動 |
| git pre-push hook | 執行 `git push`（需先跑 `setup-hooks.sh`）|

| 步驟 | 說明 |
|------|------|
| verify-claude-plugins | 驗證 Claude plugin pin |
| ruff check + format + pyright | 完整 backend 靜態分析 |
| pytest (unit, --cov ≥ 70%) | Unit test coverage 門檻 |
| pnpm lint + build + test | 前端完整驗證（TypeScript 編譯含其中）|

注意：
- `pnpm test` 是 Vitest 單元測試，不應執行 `frontend/e2e/*.spec.ts`
- Playwright E2E 測試請用 `pnpm e2e`；若 CI 在前端 `Test` 步驟出現 `test.describe()` 錯誤，通常是 Vitest 設定誤收了 `e2e/**`
- Python 變更請同時注意 `ruff check` 與 `ruff format --check`；長行或格式偏差常在後者才被擋下

## 程式碼品質要求

### 執行測試

```bash
# 從專案根目錄（推薦）
./scripts/dev-test.sh                              # 全部測試
./scripts/dev-test.sh --cov --cov-report=term-missing  # 含 coverage
```

Coverage 門檻：CI／`pre-push` hook 強制 **70%**（見 `.github/workflows/ci.yaml` 與 `scripts/pre-push.sh`）；`backend/pyproject.toml` 的 `fail_under` 設為 **80%**，本地 `uv run pytest --cov` 直接呼叫時會套用較高門檻。目標仍是 80%。

### Lint & Type Check

```bash
./scripts/dev-lint.sh    # ruff check + format check + pyright
```

個別執行（於 `backend/` 目錄）：

```bash
uv run ruff check .      # lint
uv run ruff format .     # auto-format
uv run pyright           # type check
```

### TDD 工作流

新功能與 bug fix 遵循 RED-GREEN-REFACTOR：

1. 先寫失敗的測試（RED）
2. 寫最小實作讓測試通過（GREEN）
3. 重構，確認測試仍通過（REFACTOR）

## PR 提交清單

在提交 PR 前確認：

- [ ] 測試通過：`./scripts/dev-test.sh`
- [ ] Coverage ≥ 70%（CI 門檻，目標 80%）：`./scripts/dev-test.sh --cov`
- [ ] Lint 通過：`./scripts/dev-lint.sh`
- [ ] 新功能有對應的 unit / integration tests
- [ ] Commit messages 符合 Conventional Commits 格式
- [ ] PR 說明包含：變更摘要、測試方式、相關 issue（若有）
- [ ] 不含硬編碼密鑰或敏感資料（`.env` 等不應進 PR）
