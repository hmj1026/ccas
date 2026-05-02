---
paths:
  - "**/*.py"
  - "**/*.md"
  - "**/*.yaml"
  - "**/*.toml"
---
# Claude Code 執行策略

## 任務模式

預設直接執行使用者目標，不先過度規劃。
所有流程末段均為強制後置步驟（見下方）。

| 任務規模 | 流程 |
|---------|------|
| **Small change（非 bug fix）** | inspect → patch |
| **Small change（根因已知的 bug fix）** | inspect → tdd（寫測試 RED）→ patch → tdd（驗測試 GREEN） |
| **Medium change** | inspect → brief plan → tdd → patch |
| **Bug fix（根因未知）** | bug-investigation → tdd → patch |
| **New feature** | [OpenSpec?]¹ → tdd → patch |
| **Architecture change** | software-architecture → [OpenSpec?]¹ → tdd → patch |

¹ `[OpenSpec?]` = 可選步驟，主動詢問使用者（預設 n）：
- **y** → `/opsx:new`，建立 `openspec/changes/<name>/` artifacts
- **n** → brief plan（回覆中列步驟），不建立 artifact

## 強制後置步驟（無例外、無條件豁免）

| 觸發條件 | 必須啟動 Agent | 執行時機 |
|---------|--------------|---------|
| 任何 Edit/Write | `python-reviewer`（ECC） | 最後一步 |
| bug fix 或新功能 | `tdd-guide`（ECC） | python-reviewer 之前 |
| SQL / Alembic 操作 | `database-reviewer`（ECC） | python-reviewer 之前 |
| 認證/輸入驗證/密鑰 | `security-reviewer`（ECC） | python-reviewer 之前 |

**執行順序**（若多項觸發）：tdd-guide → database-reviewer → security-reviewer → python-reviewer

**豁免條款**：
- 純研究/規劃（無任何 Edit/Write）→ 不跑 python-reviewer
- **Small change（inspect → patch，非 bug fix，非功能）→ hooks 靜態分析已足夠，不強制 python-reviewer**

## Output Contract

每次任務回覆格式：
```
結論（做了什麼）
→ 變更檔案（列表）
→ 驗證（如何確認正確）
→ 風險/待確認（若有）
```

## Anti-Loop Protocol

同一問題連續失敗 3 次，**立即停止**並回報：
1. **嘗試紀錄**：做了什麼、錯誤訊息
2. **替代方案**：至少 2 個可行路徑與代價
3. **建議決策**：推薦下一步與原因

## OpenSpec 工作流

Artifacts 目錄：`openspec/changes/<name>/`（proposal → specs → design → tasks → archive）

**IMPORTANT：tasks.md 必須先建立才能開始實作；禁止先寫程式再補文件。**

## ECC Agent Roster

> 本表所列 agent 皆來自外部 `everything-claude-code` plugin，**不在本專案 vendor 或複製維護**；execution-policy 僅規範「何時觸發」，不管理 agent 本體。

| Phase | Agent | Slash Command | When |
|-------|-------|--------------|------|
| Planning | `planner` | `/plan` | Complex features, multi-file changes |
| Architecture | `architect` | -- | System design decisions |
| TDD | `tdd-guide` | `/tdd` | Before writing implementation code |
| Code Review | `python-reviewer` | `/python-review` | After Python code changes |
| Code Review | `code-reviewer` | `/code-review` | After any code changes |
| Security | `security-reviewer` | -- | Auth, user input, API endpoints, secrets |
| Database | `database-reviewer` | -- | SQLAlchemy queries, schema design, migrations |
| Build Fix | `build-error-resolver` | `/build-fix` | Build or type errors |
| Docs | `doc-updater` | `/update-docs` | Documentation updates |

Relevant ECC skills: `python-patterns`, `python-testing`, `backend-patterns`, `api-design`, `database-migrations`, `tdd-workflow`, `security-review`, `docker-patterns`

## 自檢清單（每次任務回覆前）

| # | 觸發條件 | 必查項 | 對應規範 |
|---|---|---|---|
| 0 | **這是 small change？**（inspect → patch；非 bug fix；非新功能；**且未動到任何 SSOT 列表中的檔**） | hooks 警告處理；跳過 1-7 | 本檔「任務模式」 |
| 1 | Edit/Write Python 功能後 | `python-reviewer` 已跑？ | 本檔「強制後置步驟」 |
| 2 | Bug fix 或新功能 | `tdd-guide` 已跑？ | 本檔「強制後置步驟」 |
| 3 | SQL / Alembic 修改 | `database-reviewer` 已跑？migration 已 `alembic upgrade head` 過？ | `python-db.md` |
| 4 | 任一 Python 檔修改 | `ruff check` + **`ruff format --check`** 都過？（避免 CI 因格式失敗） | `python.md` |
| 5 | Frontend 測試設定 / `frontend/e2e/*.spec.ts` 修改 | 區分 runner：`pnpm test` = Vitest（`src/**`）；Playwright 走 `pnpm e2e` | `frontend-typescript.md` |
| 6 | **任一 SSOT 列表中的檔修改**（`scripts/docker-entrypoint.sh`、`scripts/check-env.sh`、`.env.example`、`config/*.example.yaml`） | `./scripts/sync-docker-image-assets.sh` 已跑？mirror 已 stage？ | `docker-deploy.md` 「SSOT Sync」 |
| 7 | Dockerfile / docker-compose 修改 | `docker compose config` validate 過；prod stage 改動需本機 build 一次驗證 | `docker-deploy.md` |

**第 0 項 small change 豁免條件**：「touched 任一 SSOT 列表中的檔則不算 small change」（避免 SSOT 漂移情境又落入豁免）。

## PostToolUse Hooks（hook 與 rule 的對應）

下列 hook 由 `.claude/settings.json` 在 Edit/Write 後自動跑，是**警告層**、不取代 rules。一條紀律若被 hook 覆蓋，仍應在 rules 中以人類可讀文字寫一遍。

| Hook | 覆蓋範圍 | 對應 rule |
|---|---|---|
| `ccas-python-lint.sh` | Python Edit/Write 即時 ruff + bandit 警告 | `python.md` |
| `ccas-sqlalchemy-model-check.sh` | `**/models*.py` 即時驗 ORM 慣例 | `python-db.md` |
| `ccas-tdd-red-check.sh` | `tests/` 新增測試後跑該檔確認 RED | `python-testing.md` |
| `ccas-frontend-lint.sh` | `frontend/**/*.{ts,tsx}` 即時 eslint | `frontend-typescript.md` |
| `ccas-alembic-migration-check.sh` | migration 檔即時驗安全性（drop column 警告等） | `python-db.md` |
| `ccas-docker-check.sh` | Dockerfile / compose 即時驗慣例 | `docker-deploy.md` |
| `ccas-pre-push-stop.sh`（Stop event） | session 結束跑 pre-push 完整檢查 | `docker-deploy.md` 「Repo-level Process Gates」 |
| `ccas-session-retrospective.sh`（Stop） | 寫 session log | — |
