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
| Bug 根因追查 | `bug-investigation`（Anthropic 內建） |
| 架構決策 / 模組邊界 | `software-architecture`（Anthropic 內建） |
| 完整產品驗收、QA 測試、smoke test | `ccas-qa-acceptance` |

> 上表只列 7 個常用情境。其他 skill 由 `npx skills` CLI 套件 / Claude plugin 同步到 `.agents/skills/` 或 `.claude/skills/`，對應觸發詞時自動匹配；明細與邊界規範見「外部依賴與 skill 邊界」段。

## Rules 指標（`.claude/rules/`）

- **execution-policy.md** — 任務分類流程、強制後置步驟、ECC agent roster、自檢清單、PostToolUse hooks 對應
- **skill-policy.md** — 多 skill 命中時的選用優先順序
- **python.md / python-api.md / python-db.md / python-testing.md** — 後端慣例
- **frontend-typescript.md** — 前端慣例
- **parser-development.md** — Bank parser registry pattern 與 PDF 解析慣例
- **docker-deploy.md** — 容器、部署、SSOT sync、repo-level process gates 慣例

## Key Conventions

- 所有回應一律用**正體中文**
- 變更命名採 **kebab-case**（如 `add-user-auth`）
- **CLAUDE.md 為 SSOT**（專案說明的單一真實來源）
- Skills 對輸入模糊時用 `AskUserQuestion` 澄清，不要猜
- Task 進度以 markdown checkbox（`- [ ]` / `- [x]`）在 tasks artifact 中追蹤
- Delta specs 在 archive 時同步到 `openspec/specs/`

## 外部依賴與 skill 邊界

### Skill 三個來源主體

| # | 來源 | 安裝方式 | 落點 |
|---|---|---|---|
| 1 | `npx skills` CLI 套件 | `npx skills add <repo>` → 寫 `skills-lock.json` | `.agents/skills/<x>/` 實體 + 各 agent 目錄 symlink |
| 2 | Claude plugin（manifest 提供 agent / slash / hook / 部分 skill） | `.claude/settings.json` `enabledPlugins` 啟用 | `.claude/skills/<x>` 實體目錄（plugin 自帶） |
| 3 | 自寫 skill（為跨 agent runtime 共用而刻意放 `.agents/`） | 手動建立或 `npx skills init` | `.agents/skills/<x>/` 實體 + agent symlink |

外加 Anthropic 內建 skill：直接在 `.claude/skills/<x>` 實體目錄（如 `bug-investigation`、`software-architecture`、`frontend-design`），無需安裝。

### 目錄紀律

**`.agents/skills/` — 跨 agent 共用 storage**
- 進入途徑：`npx skills add` 安裝（含 ECC reference skills 等）/ 自寫且明確要跨 agent 共用的 skill
- ✗ 不手動 `cp` / `mv` / `rm` 套件條目（要動套件用 `npx skills add/remove/update`）
- ✓ 自寫 skill 視同一般原始碼，可直接 git 操作

**`.claude/skills/` — Claude 載入點**
- 進入途徑：`npx skills` CLI 建立的 symlink（多數）/ Claude plugin manifest 寫入的實體目錄（`openspec-*` 等）/ Anthropic 內建 skill
- ✗ 不手動 vendor、不手動建立實體目錄繞過上述三條途徑
- ✗ 不手改 symlink；要改內容請改 `.agents/skills/<x>` 本體（且只對自寫 skill 適用）

### 外部 plugin / 套件清單（不 vendor、不手動同步）

下列來源由各自 manifest / lock 檔維護，**本專案不複製、不跨平台同步、不列入本專案變更範圍**：

- `everything-claude-code` — 同時透過兩條途徑：plugin manifest 提供 agent / slash command（落 `.claude/`）+ `npx skills` 套件 `affaan-m/everything-claude-code` 提供 reference SKILL.md（落 `.agents/skills/`，由 `skills-lock.json` 追蹤）
- `openspec` CLI 套件 — `.claude/skills/openspec-*/` 與 `.claude/commands/opsx/`
- `codex` plugin、`pyright-lsp` plugin — 見 `.claude/settings.json` `enabledPlugins`

### 自寫共用 skill（CCAS 自有）

下列為本專案自寫、刻意放 `.agents/skills/` 以跨 agent runtime 共用：

- `ccas-dev-commands` — 日常指令（測試 / lint / pipeline / server / alembic / seed）
- `ccas-env-config` — `.env` / Vite proxy / Docker env_file 設定
- `ccas-qa-acceptance` — 完整產品驗收 / QA / smoke test
- `ccas-tech-stack` — 技術棧總覽 / onboarding
