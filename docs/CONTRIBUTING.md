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

## 程式碼品質要求

### 執行測試

```bash
# 從專案根目錄（推薦）
./scripts/dev-test.sh                              # 全部測試
./scripts/dev-test.sh --cov --cov-report=term-missing  # 含 coverage
```

Coverage 門檻：**80%**。低於門檻時 CI 會失敗。

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
- [ ] Coverage ≥ 80%：`./scripts/dev-test.sh --cov`
- [ ] Lint 通過：`./scripts/dev-lint.sh`
- [ ] 新功能有對應的 unit / integration tests
- [ ] Commit messages 符合 Conventional Commits 格式
- [ ] PR 說明包含：變更摘要、測試方式、相關 issue（若有）
- [ ] 不含硬編碼密鑰或敏感資料（`.env` 等不應進 PR）
