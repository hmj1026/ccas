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

0. **這是 small change（inspect → patch，非功能/bug fix）？** → 僅確認 hooks 警告，跳過 1-3
1. **Edit/Write Python 功能後？** → python-reviewer 已跑？ YES/NO
2. **Bug fix/新功能？** → tdd-guide 已跑？ YES/NO
3. **SQL/Alembic 修改？** → database-reviewer 已跑？ YES/NO
