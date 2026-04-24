# CLAUDE.md

CCAS（Credit Card Automation System）— 信用卡帳單自動化 pipeline：Gmail PDF → 解密 → 解析 → 分類 → REST API / Telegram 通知。

## 按需載入的 Skill 指標

遇到下列情境時，對應 skill 會自動被索引載入（或可手動呼叫）：

| 情境 | Skill |
|---|---|
| 執行測試 / lint / pipeline / server / alembic / seed 等日常指令 | `ccas-dev-commands` |
| 技術棧總覽、新人 onboarding、評估技術選型 | `ccas-tech-stack` |
| `.env`、環境變數、Vite proxy、Docker env_file | `ccas-env-config` |
| OpenSpec spec-driven 流程（proposal → specs → design → tasks → archive） | `/opsx:*` 系列（外部套件提供） |
| Bug 根因追查 | `bug-investigation`（外部） |
| 架構決策 / 模組邊界 | `software-architecture`（外部） |
| 完整產品驗收、QA 測試、smoke test | `ccas-qa-acceptance` |

## Rules 指標（`.claude/rules/`）

- **execution-policy.md** — 任務分類流程、強制後置步驟、ECC agent roster
- **skill-policy.md** — 多 skill 命中時的選用優先順序
- **python.md / python-api.md / python-db.md / python-testing.md** — 後端慣例
- **frontend-typescript.md** — 前端慣例
- **docker-deploy.md** — 容器與部署慣例

## Key Conventions

- 所有回應一律用**正體中文**
- 變更命名採 **kebab-case**（如 `add-user-auth`）
- **CLAUDE.md 為 SSOT**（專案說明的單一真實來源）
- Skills 對輸入模糊時用 `AskUserQuestion` 澄清，不要猜
- Task 進度以 markdown checkbox（`- [ ]` / `- [x]`）在 tasks artifact 中追蹤
- Delta specs 在 archive 時同步到 `openspec/specs/`

## 外部依賴（不 vendor、不手動同步）

本專案使用以下外部來源的 skills / commands / plugins，**不複製、不跨平台同步、不列入本專案變更範圍**：

- `openspec` CLI 套件（提供 `.claude/skills/openspec-*/` 與 `.claude/commands/opsx/`）
- `everything-claude-code` plugin（提供 python-reviewer、tdd-guide、database-reviewer、security-reviewer 等 agents 與 reference skills）
- `codex` plugin、`pyright-lsp` plugin（見 `.claude/settings.json`）
- `skills-lock.json` 管理的 `affaan-m/everything-claude-code` 條目

外部套件的維護、版本、跨平台支援由套件本身負責。
