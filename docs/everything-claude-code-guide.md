# Everything Claude Code (ECC) 使用指南

> 本指南涵蓋 Claude Code 的 `everything-claude-code` plugin 提供的 100+ skills 與 60+ commands。聚焦於 CCAS 專案的實際需求，並完整說明 ECC 特有的 instinct 持續學習系統。

**文件版本**：2026-04-13  
**適用專案**：CCAS（信用卡帳單自動化系統）  
**更新週期**：每季

---

## 1. 概覽

### ECC 是什麼？

Everything Claude Code (ECC) 是一個外部 plugin，提供：

- **100+ 專案導向 skills**：從 TDD、安全審查、資料庫遷移到 Docker、CI/CD 的專業指引
- **60+ user-invocable commands**：快速啟動工作流、session 管理、持續學習操作
- **6 層代理系統**：Haiku（觀察）、Sonnet（實作）、Opus（架構）協調工作
- **Instinct 自學系統**：從 git history 觀察、從行為學習、自動演進成可重用 skills

### 三層架構

```
┌─────────────────────────────────────────┐
│   INFRASTRUCTURE LAYER (Infrastructure) │
│  設定、初始化、專案發現                   │
│  ├─ configure-ecc      (首次安裝)        │
│  └─ codebase-onboarding (新專案上手)    │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│   GOVERNANCE LAYER (行為管理)            │
│  工作流指引、品質標準、context 監控      │
│  ├─ agentic-engineering  (工作方式)      │
│  ├─ context-budget       (資源監控)      │
│  └─ rules-distill        (原則提煉)      │
└─────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────┐
│   LEARNING LAYER (學習與記憶)            │
│  觀察、檢測、評分、演進、晉升            │
│  ├─ continuous-learning-v2 (學習引擎)    │
│  ├─ autonomous-loops       (執行模式)    │
│  ├─ /promote, /prune       (維護命令)    │
│  └─ instinct-system        (持續改進)    │
└─────────────────────────────────────────┘
```

---

## 2. 核心開發工作流（日常最常用）

### 2.1 規劃階段：`/everything-claude-code:plan`

**目的**：重述需求、評估風險、產生 step-by-step 實作計劃。在 Claude 動手前等候使用者確認。

**何時使用**：
- 新功能設計階段
- 複雜多檔案重構
- 需求不明確或跨領域協調

**用法**：
```bash
/everything-claude-code:plan 新增 Telegram 通知功能，支援帳單解析完成的即時通知
```

**重要注意事項**：
- 計劃產出後，Claude 會 **完全停止** 等候確認（CRITICAL）
- 若需修改，回應 `修改：[變更項目]` 後再確認
- 確認後配合 `/tdd` 進行實作或 `/code-review` 進行審查

---

### 2.2 TDD 工作流：`/everything-claude-code:tdd`

**目的**：強制執行嚴格的 RED → GREEN → REFACTOR TDD 循環。

**何時使用**：
- 實作任何新函數或功能
- 修復已知根因的 bug
- 希望強制執行 TDD 紀律

**工作流**：
```
1. RED：寫一個會失敗的測試（務必執行確認失敗）
2. 確認 RED：pytest 輸出 FAILED
3. GREEN：實作最小化程式碼使測試通過
4. 確認 GREEN：pytest 輸出 PASSED
5. REFACTOR：優化程式碼（不改功能）
6. 驗證覆蓋率：80% 以上
```

**用法範例**：
```bash
/everything-claude-code:tdd 計算市場流動性分數函數
```

**覆蓋率要求**：
- 一般程式碼：80% 以上
- 金融計算：100%
- 認證、授權：100%
- 安全關鍵程式碼：100%

**重要注意事項**：
- 未實際執行的測試 **不算 RED** — 必須 compile 且 run 一次看到 FAIL
- Git checkpoint commits：
  - RED：`test: add reproducer for <feature>`
  - GREEN：`fix: <feature>`
  - REFACTOR：`refactor: clean up after <feature>`
- 不要 squash checkpoints 直到整個循環完成

---

### 2.3 Python 程式碼審查：`/everything-claude-code:python-review`

**目的**：全面 Python 審查，涵蓋 PEP 8、type hints、安全性、Pythonic 習慣用法。

**何時使用**：
- 改動任何 `.py` 檔案後
- 提交 commit 前
- 審查他人 PR

**檢查項目**（自動執行）：
- `mypy` — 型別檢查
- `ruff check .` — 快速 linting
- `black --check` — 程式碼格式
- `isort` — import 排序
- `bandit` — 安全掃描
- `pip-audit` — 依賴安全
- `safety check` — Python 安全資料庫
- `pytest --cov` — 測試覆蓋率

**用法**：
```bash
/everything-claude-code:python-review
```

**嚴重程度等級**：
- **CRITICAL**：阻止合併
- **HIGH**：應該修復
- **MEDIUM**：考慮修復

**重要注意事項**：
- 自動偵測 `git diff` 中的 `.py` 檔案
- Django 特定檢查：N+1 queries、migration 問題
- 裁決：CRITICAL/HIGH = FAIL（阻止），僅 MEDIUM = WARNING（通過）

---

### 2.4 通用程式碼審查：`/everything-claude-code:code-review`

**目的**：語言無關的程式碼審查或 GitHub PR 審查。

**何時使用**：
- 非 Python 語言的程式碼
- 審查完整 GitHub PR（傳 PR 號）
- 一般品質審查

**用法**：
```bash
/everything-claude-code:code-review                    # 審查未 commit 變更
/everything-claude-code:code-review <PR-URL>          # 審查 PR
/everything-claude-code:code-review org/repo#123      # GitHub PR
```

---

### 2.5 旁支問題：`/everything-claude-code:aside`

**目的**：快速回答旁支問題，不打斷當前任務，答完自動恢復。

**何時使用**：
- 對當前工作產生疑問
- 需要快速澄清或第二意見
- 不想中斷工作流

**用法**：
```bash
/everything-claude-code:aside fetchWithRetry() 到底在幹什麼？
```

**重要注意事項**：
- 旁支期間：唯讀，不修改檔案
- 答題後：自動回到原任務，狀態保留
- 若發現問題：會先報告而非直接恢復

---

## 3. 品質閘道

### 3.1 雙模型對抗審查：`/everything-claude-code:santa-loop`

**目的**：兩個獨立審查者都必須通過，程式碼才能 push。自動修復與重審，最多 3 輪。

**何時使用**：
- 高品質要求的變更
- 想要多視角審查（非單一 LLM）
- 推上 main 前的最終確認

**審查者**：
- Reviewer A：Claude Opus（固定）
- Reviewer B：優先用 `codex` (GPT-5.4) 或 `gemini` (Gemini 2.5 Pro)；若無則回落 Claude Opus

**用法**：
```bash
/everything-claude-code:santa-loop                     # 所有未 commit 變更
/everything-claude-code:santa-loop src/auth/           # 特定目錄
/everything-claude-code:santa-loop "add telegram"     # 描述
```

**流程**：
```
Round 1: Reviewer A 審查 → NAUGHTY?
           ↓ YES → 自動修復 → Commit → 重審
           ↓ NO → 進入 Round 2

Round 2: Reviewer B 審查 → 同上

Round 3: 雙審查都 NICE？
           ↓ YES → PUSH
           ↓ NO → 報告錯誤，等待使用者介入
```

**重要注意事項**：
- 最多 3 輪；第 3 輪後仍 NAUGHTY 則停止
- 每輪都會 commit，工作不會遺失
- Push 只發生在雙審查都 PASS 後

---

### 3.2 6-Phase 驗證迴圈：`verification-loop` skill

**目的**：PR 前的多層驗證，產出標準化 PASS/FAIL 報告。

**何時使用**：
- 功能完成前最後驗證
- 準備合併 PR
- 重構後的品質確認

**6 個驗證階段**（按序執行，任一失敗則停止）：

| 階段 | 檢查項 | Python 命令 |
|------|--------|-----------|
| 1. Build | 編譯/打包 | `python -m py_compile` |
| 2. Type Check | 型別檢查 | `pyright` |
| 3. Lint | 程式碼風格 | `ruff check .` |
| 4. Tests | 單元+整合測試 | `pytest --cov` |
| 5. Security | 安全掃描 | grep hardcoded keys |
| 6. Diff Review | 變更審查 | `git diff --stat` |

**報告範例**：
```
VERIFICATION REPORT
==================
Build:     PASS
Types:     PASS (0 errors)
Lint:      PASS (2 warnings)
Tests:     PASS (47/47 passed, 84% coverage)
Security:  PASS (0 issues)
Diff:      3 files changed
Overall:   READY for PR
```

**用法**：
```bash
# 使用 skill 直接觸發
verification-loop skill 或手動檢查上述 6 個階段
```

---

### 3.3 Context 預算審計：`/everything-claude-code:context-budget`

**目的**：審計 context window 用量，找出浪費來源，產生優先順序建議。

**何時使用**：
- 接近 context 限額
- 想優化 context 使用效率
- 診斷哪些組件佔用最多 token

**用法**：
```bash
/everything-claude-code:context-budget
/everything-claude-code:context-budget --verbose
```

**主要消耗源**（降序）：
1. MCP tool schemas（每個 ~500 tokens）
2. Agent descriptions（每個觸發都載入）
3. Rules 檔案（每次 load）
4. Skills 內容
5. 歷史訊息

**重要注意事項**：
- 200K context 預設；若改用 Opus 需調整假設
- 移除未使用 MCP 最有效

---

## 4. Session 管理

### 4.1 儲存 Session：`/everything-claude-code:save-session`

**目的**：捕捉當前工作狀態（完成、失敗、剩餘工作）到 `~/.claude/session-data/` 供下次恢復。

**何時使用**：
- 收工前（重要！）
- 接近 context 限額
- 解決複雜問題值得記錄
- 交接工作給未來的自己

**用法**：
```bash
/everything-claude-code:save-session
```

**儲存格式**：
- 檔名：`YYYY-MM-DD-<短ID>-session.tmp`
- 例：`2026-04-13-abc123de-session.tmp`
- 儲存位置：`~/.claude/session-data/`

**儲存內容結構**：
```
PROJECT: ccas
CURRENT STATE:
  - 已完成：features X, Y
  - 進行中：feature Z（80% 完成）
  - 檔案修改：src/auth/login.py, src/api/endpoints.py

WHAT DID NOT WORK:
  - 方案 A 因為 N+1 query 問題失敗（記住避免這個）
  - JWT token 路由方案改成了 session cookie

OPEN QUESTIONS:
  - Telegram API rate limit 需要確認
  - DB migration 策略（expand-contract 或一次性？）

NEXT STEP:
  - 寫 Telegram 推送的單元測試
  - 實施 rate limiter middleware
```

**重要注意事項**：
- **「未奏效」章節最關鍵** — 防止下次盲目重試
- 每個 session 獨立檔案，不會覆蓋
- 需要確認才會最終化（防止誤按）

---

### 4.2 恢復 Session：`/everything-claude-code:resume-session`

**目的**：載入最近的 session 檔案，產生結構化簡報後恢復工作。

**何時使用**：
- 新 session 開始時（會自動偵測之前的工作）
- Context 滿後重新開始
- 接收同事的 session 檔案

**用法**：
```bash
/everything-claude-code:resume-session                          # 載入最近
/everything-claude-code:resume-session 2026-04-13              # 指定日期
/everything-claude-code:resume-session ~/.claude/session-data/abc.tmp  # 指定檔案
```

**回傳結構**：
```
PROJECT: ccas
WHAT WE'RE BUILDING: Telegram 實時帳單通知
CURRENT STATE: 核心解析完成，正在整合推送

WHAT NOT TO RETRY:
  × JWT 路由方案（已改成 session cookie）
  × 同步 API 調用（用 Celery queue 了）

OPEN QUESTIONS:
  ? Rate limit 策略確認中
  ? DB migration timing

NEXT STEP:
  → 寫 Telegram 推送單元測試
```

**重要注意事項**：
- 簡報後停止等待使用者指示（不會自動繼續工作）
- 若 session 檔案 > 7 天或參考檔案遺失會警告
- 唯讀（不會修改 session 檔案）

---

### 4.3 旁支問題（已在 2.5 涵蓋）

見 **2.5 旁支問題** 章節。

---

## 5. Instinct 持續學習系統

### 5.1 系統概述

ECC 的核心創新是 **自動學習系統**，從觀察、分析、評分、演進、晉升、清理的完整循環。

```
SESSION HOOKS (100% reliable)
    ↓ 紀錄每個 tool call
    ↓
OBSERVE: ~/.claude/homunculus/projects/<hash>/observations.jsonl
    ↓ 累積 20+ 觀察後
    ↓ 每 5 分鐘一次後台 Haiku agent
    ↓
DETECT: 識別模式（用戶修正、錯誤解決、重複工作流）
    ↓
SCORE: confidence 0.3~0.9（根據重複性和修正反饋）
    ↓
INSTINCT: ~/.claude/homunculus/projects/<hash>/instincts/personal/ 或 ~/.claude/homunculus/instincts/personal/（全域）
    ↓
EVOLVE: /evolve 聚合相關 instincts → Skill / Command / Agent
    ↓
PROMOTE: avg confidence ≥ 0.8 跨 2+ 專案 → 晉升全域
    ↓
RULES DISTILL: 2+ skills 共同原則 → rules 檔案
    ↓
SKILL COMPLY: /skill-comply 驗證 skill 是否真的被遵守
```

### 5.2 Instinct 生命週期（詳細）

#### 階段 1：OBSERVE（100% 可靠）

**實現機制**：Hooks（PreToolUse / PostToolUse）在每個 tool call 時觸發，記錄事件到 `observations.jsonl`

**記錄項目**：
- Tool 名稱與參數
- 輸出與副作用
- 執行時間
- 錯誤或警告
- 使用者的修正反應

---

#### 階段 2：DETECT（自動分析）

**觸發機制**：後台 Haiku agent，每 5 分鐘檢查一次（若觀察 ≥ 20）

**檢測模式**：
- 使用者明確更正 Claude（**高信號**）
- 反覆遇到相同錯誤的解決方法（**中信號**）
- 相同工作流序列出現 2+ 次（**低信號**）
- 環境相關模式（OS、Python 版本等）

**例子**：
- 「我寫錯 SQL 了，改成 parameterized query」→ 檢測到 SQL injection 預防模式
- 「pytest 第三次失敗，加 `-v` flag 後通過」→ 檢測到 pytest verbose 模式
- 「新增 Django model 後自動跑 makemigrations」→ 檢測到 Django workflow

---

#### 階段 3：SCORE（信心評分）

**初始分數**：0.5（中等信心）

**提升因素** (+0.1 per observation)：
- 模式在同一 session 中重複
- 模式跨 session 持續出現
- 使用者未更正此模式

**降低因素** (-0.2 per correction)：
- 使用者明確更正此模式
- Skill/Rule 已存在處理此情況
- 模式專案特定但被標示全域

**上下界**：0.3（最低）~ 0.9（最高）

---

#### 階段 4：EVOLVE（結構化）

**何時觸發**：手動 `/evolve` 或自動（當 2+ 相關 instincts 累積時）

**聚合規則**：

| 條件 | 目標結構 |
|------|---------|
| 2+ instincts，同觸發源 | Skill（詳細指引） |
| 3+ instincts，用戶呼叫序列 | Command（快捷命令） |
| 複雜多步驟，獨立執行 | Agent（自主代理） |

**用法**：
```bash
/everything-claude-code:evolve              # 分析並建議
/everything-claude-code:evolve --generate   # 產出檔案
```

---

#### 階段 5：PROMOTE（跨專案提升）

**晉升條件**：
- 同一 instinct ID 出現在 2+ 專案
- 平均 confidence ≥ 0.8
- 手動 `/promote` 命令

**效果**：
- 從 `projects/<hash>/instincts/` 移動到 `instincts/`（全域）
- 所有專案都繼承此 instinct

**用法**：
```bash
/everything-claude-code:promote
```

**例子**：
- 「總是驗證使用者輸入」→ 在多個專案中確認 → 提升全域
- Python type hints 最佳實踐 → 跨所有 Python 專案 → 全域

---

#### 階段 6：PRUNE（清理）

**清理規則**：刪除超過 30 天未審視的待處理 instincts

**用法**：
```bash
/everything-claude-code:prune
```

**保留標準**：
- confidence ≥ 0.7
- 近 30 天有觀察
- 已由使用者確認

---

### 5.3 Instinct 相關命令

#### `instinct-status`

**目的**：查看當前專案 + 全域的所有 learned instincts，帶信心分數

**用法**：
```bash
/everything-claude-code:instinct-status
```

**輸出範例**：
```
PROJECT INSTINCTS (ccas)
━━━━━━━━━━━━━━━━━━━━━━━━
Domain: testing
  ✓ [████████░░] pytest fixture isolation  (0.85, 12 obs)
  ◐ [██████░░░░] async test timeout       (0.62, 5 obs)

Domain: django
  ✓ [██████████] N+1 query prevention     (0.92, 24 obs)
  ✓ [████████░░] migration expand-contract (0.88, 18 obs)

GLOBAL INSTINCTS
━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ [██████████] Input validation always (0.91, 143 obs)
  ✓ [████████░░] Never hardcode secrets  (0.89, 67 obs)
```

---

#### `instinct-export`

**目的**：匯出 instincts 到 YAML 檔供分享、轉移機器、貢獻團隊

**用法**：
```bash
# 全部匯出
/everything-claude-code:instinct-export --output my-instincts.yaml

# 篩選：只匯出「testing」domain 且 confidence ≥ 0.7
/everything-claude-code:instinct-export --domain testing --min-confidence 0.7

# 專案範圍
/everything-claude-code:instinct-export --scope project

# 輸出格式：YAML
instincts:
  - id: pytest-fixture-isolation-xyz
    trigger: "When a test modifies a fixture state"
    action: "Use function-scoped fixtures or conftest reset"
    confidence: 0.85
    domain: testing
    scope: project
    project: ccas
```

---

#### `instinct-import`

**目的**：從本地 YAML 或 URL 匯入 instincts，自動去重與版本合併

**用法**：
```bash
# 本地檔案
/everything-claude-code:instinct-import ./team-instincts.yaml

# 遠端 URL
/everything-claude-code:instinct-import https://github.com/org/repo/instincts.yaml

# 預覽（不修改）
/everything-claude-code:instinct-import ./team.yaml --dry-run

# 篩選與範圍
/everything-claude-code:instinct-import team.yaml --min-confidence 0.8 --scope project
```

**合併策略**：
- 相同 ID，新檔 confidence 更高 → 更新
- 相同 ID，新檔 confidence 更低 → 保留舊版本
- 新 ID → 插入（標記 `source: inherited`）

---

#### `evolve`

**已在 5.2 段落詳述。**

---

#### `promote`

**已在 5.2 段落詳述。**

---

#### `prune`

**已在 5.2 段落詳述。**

---

#### `learn-eval`

**目的**：從當前 session 萃取可重用模式，評估品質，決定儲存位置（專案 vs 全域），再存檔。

**何時使用**：
- 解決非平凡問題後
- 想保存學習但不確定品質

**用法**：
```bash
/everything-claude-code:learn-eval
```

**品質閘道**（強制檢查清單）：

- [ ] 與既有 skills 無重複
- [ ] 可在其他類似情境重用（非一次性修復）
- [ ] 觸發條件明確（非模糊的「有時候」）
- [ ] 決策：**Save** / **Improve then Save** / **Absorb into [existing]** / **Drop**

**儲存決策**：
- **全域** (`~/.claude/skills/learned/`)：跨專案通用（e.g., 輸入驗證）
- **專案** (`.claude/skills/learned/`)：專案特定（e.g., CCAS 的 PDF 解析技巧）
- **吸收** (`skills/XYZ/SKILL.md`)：附加到既有 skill

**重要注意事項**：
- 不抽取瑣碎修復（typos、語法錯誤）
- 不抽取一次性問題
- 品質 > 數量

---

## 6. Skill 管理與維護

### 6.1 從 Git History 生成 Skill：`skill-create`

**目的**：分析 git commit history，自動萃取編碼模式，產出 `SKILL.md` 檔。

**何時使用**：
- 上手新專案（bootstrap skills from past work）
- 提煉團隊慣例成正式 skill

**用法**：
```bash
# 預設：分析最近 200 commits
/everything-claude-code:skill-create

# 自訂 commit 數量
/everything-claude-code:skill-create --commits 100

# 同時產生 instinct 檔
/everything-claude-code:skill-create --commits 100 --instincts

# 自訂輸出目錄
/everything-claude-code:skill-create --output ~/.claude/skills/learned/
```

**檢測模式**：
- Conventional commits 規則（feat:, fix:, refactor:）
- 檔案共變（哪些檔案常一起改）
- 工作流序列（每次做功能前都執行的步驟？）
- 架構決策（import 模式、目錄結構）
- 測試慣例（test-first？ 涵蓋率目標？）

---

### 6.2 Skill 健康度儀表板：`skill-health`

**目的**：顯示所有 skills 的績效（成功率趨勢、常見失敗類型、待審批修訂）

**何時使用**：
- 審計 skill 績效
- 找出衰退的 skills
- 規劃 skill 演進

**用法**：
```bash
/everything-claude-code:skill-health

# 只看失敗分群
/everything-claude-code:skill-health --panel failures

# JSON 輸出（機器使用）
/everything-claude-code:skill-health --json
```

**儀表板面板**：
1. **Success Rate（30 天）**：sparkline 圖表
2. **Failure Patterns**：聚集常見失敗
3. **Pending Amendments**：待審批的改進提案
4. **Version History**：版本演進

**行動**：若 skill 衰退 → 建議執行 `/evolve`

---

### 6.3 原則提煉：`rules-distill` skill

**目的**：掃描 2+ skills，找出共通原則，寫成 `rules/*.md` 檔。

**何時使用**：
- Skill 數量 ≥ 5 後，統整原則避免重複
- 跨 skill 協調時

**用法**：
```
rules-distill skill 或手動檢查 ~/.claude/rules/ 目錄
```

**輸出範例**：從 `api-design` + `backend-patterns` + `security-review` 萃取：
```
→ 新增 rules/rest-api-fundamentals.md：
  - Never return 200 for errors
  - Always use semantic HTTP status codes
  - Parameterized queries for all DB access
```

---

### 6.4 Skill 遵守度驗證：`skill-comply` skill

**目的**：測量 agent 是否真的遵守 skills 和 rules。產出遵守度報告。

**何時使用**：
- 驗證 skill 實際效果（非紙上談兵）
- 識別規則漏洞

**用法**：
```
skill-comply skill 或在相關規則上執行驗證
```

**測試方式**（3 層嚴格度）：
1. **寬鬆**：提示含 skill 名稱提示
2. **正常**：提示不含 skill 名稱
3. **嚴格**：對抗性提示（故意激怒）

**輸出**：遵守度百分比 + tool call 時間軸

---

## 7. 語言特定 Build / Review / Test

ECC 為多種語言提供 build、review、test 三個 command。CCAS 專案主要用 Python，但列舉供參考：

### Go

| Command | 說明 |
|---------|------|
| `/everything-claude-code:go-build` | 修 build 錯誤、go vet、linter 問題 |
| `/everything-claude-code:go-review` | 慣例、concurrency、error handling |
| `/everything-claude-code:go-test` | TDD 工作流（table-driven tests） |

### Rust

| Command | 說明 |
|---------|------|
| `/everything-claude-code:rust-build` | Borrow checker、依賴問題 |
| `/everything-claude-code:rust-review` | Ownership、lifetimes、unsafe |
| `/everything-claude-code:rust-test` | TDD 工作流（cargo-llvm-cov） |

### Kotlin

| Command | 說明 |
|---------|------|
| `/everything-claude-code:kotlin-build` | Gradle build、compiler 錯誤 |
| `/everything-claude-code:kotlin-review` | Null safety、coroutine safety |
| `/everything-claude-code:kotlin-test` | TDD 工作流（Kotest + Kover） |

### C++

| Command | 說明 |
|---------|------|
| `/everything-claude-code:cpp-build` | CMake、linker 問題 |
| `/everything-claude-code:cpp-review` | 記憶體安全、modern C++ idioms |
| `/everything-claude-code:cpp-test` | TDD 工作流（GoogleTest + gcov） |

---

## 8. 常用 Skills 說明（非 Command，但可被觸發）

除了 command 外，ECC 還提供 100+ skills，可被自動觸發或手動調用。以下重點列出 CCAS 相關的 9 個：

### 8.1 python-patterns

**觸發條件**：Python 程式碼編寫 / 審查

**核心內容**：
- EAFP（Exceptions over conditionals）習慣用法
- Type hints（Python 3.9+ 內建泛型）
- 自訂例外層級（`AppError` → `ValidationError` → `NotFoundError`）
- `@contextmanager`、`__enter__`/`__exit__` 上下文管理器
- 生成器與 lazy evaluation（省記憶體）
- `@dataclass` 與 `__post_init__` 驗證
- Concurrency：`asyncio` / `ThreadPoolExecutor` 選擇
- 專案配置：`pyproject.toml` 統一（black、isort、ruff、mypy）
- 工具鏈：black、isort、ruff、mypy、bandit、pip-audit

**例子**：
```python
# WRONG: 拋出泛用 Exception
try:
    user = find_user(id)
except Exception:
    pass

# RIGHT: 特定例外，EAFP 風格
try:
    user = find_user(id)
except UserNotFoundError as e:
    logger.warning(f"User {id} not found", exc_info=e)
    return None
```

---

### 8.2 python-testing

**觸發條件**：新增測試 / TDD 流程

**核心內容**：
- pytest fixtures（function、module、session scoped）
- 參數化：`@pytest.mark.parametrize`
- Mocking：`unittest.mock` 的 `@patch`、`side_effect`、`autospec`
- 非同步測試：`pytest-asyncio`
- 自訂 markers：`@pytest.mark.slow`、`@pytest.mark.integration`
- 覆蓋率：`pytest --cov` 目標 80%+
- DB 測試隔離：`session.begin_nested()`、`rollback()`
- 常見 antipattern：shared state、內部實現測試

**例子**：
```python
@pytest.fixture(scope="function")
def db_session():
    # Setup
    with db.begin_nested():
        yield db.session
        db.session.rollback()  # 每測試後清理

def test_user_creation(db_session):
    user = User(name="Alice")
    db_session.add(user)
    db_session.commit()
    assert user.id is not None
```

---

### 8.3 security-review

**觸發條件**：實作認証/授權、API 端點、輸入驗證、支付、機密儲存

**核心內容**：
- **17 點預部署檢查清單**（絕對必要）
- 機密：全在 env vars，啟動時驗證，永遠不在 source
- 輸入驗證：schema-based（Pydantic for Python）
- SQL injection：只用 parameterized queries，絕無字串串接
- JWT：httpOnly cookies（非 localStorage），RBAC 角色
- XSS：DOMPurify、CSP headers
- CSRF：token 驗證 + SameSite=Strict
- Rate limiting：per-IP 和 per-user
- 日誌：永遠 redact 密碼/tokens/卡號，通用使用者訊息，詳細訊息只在 server 日誌
- 依賴安全：`bandit -r .`、`pip-audit`、`safety check`

**17 點清單**（節錄）：
- [ ] 所有 secrets 在 env，啟動驗證
- [ ] API 輸入 schema 驗證
- [ ] SQL 全 parameterized
- [ ] 認證端點有 rate limit
- [ ] JWT token 有過期時間
- [ ] CSRF token 在表單
- [ ] 敏感資料不入日誌
- [ ] TLS/HTTPS 強制
- [ ] CORS 明確設定（非 `*`）
- [ ] 密碼 hash（bcrypt / argon2）
- [ ] 登入嘗試限流
- [ ] 檔案上傳白名單（副檔名、MIME）
- [ ] SQL injection 檢查
- [ ] XSS 檢查
- [ ] 依賴漏洞掃描
- [ ] security headers 檢查
- [ ] 個人資料保護（PII redaction）

---

### 8.4 database-migrations

**觸發條件**：表結構變更、column 加減、索引新增、schema 重構

**核心內容**：
- **核心規則**：不直接改 production DB，一切都是 migration
- 分離：schema migrations（DDL）與 data migrations（DML）
- PostgreSQL patterns：
  - Safe nullable column add（新 column 加 DEFAULT）
  - `CREATE INDEX CONCURRENTLY`（不鎖表）
  - NOT NULL column safety（先加 nullable，backfill，再轉 NOT NULL）
- Expand-contract pattern（零停機 rename）：
  1. 新增 column
  2. 應用層同時寫新舊 column
  3. 後台 backfill 舊值到新 column
  4. 改應用層只讀新 column
  5. 刪舊 column
- Batch data migration（大表）：`FOR UPDATE SKIP LOCKED` + commit per batch
- Django 特定：
  - `makemigrations`、`migrate`
  - `RunPython` 自訂 migration
  - `SeparateDatabaseAndState`（解耦 model state 與 DB）
- 反 pattern：編輯已部署 migration、NOT NULL 無 DEFAULT、一個 migration 混 DDL+DML

**例子（Django）**：
```python
# Bad: 一個 migration 混 DDL + DML
operations = [
    AddField('user', 'premium', models.BooleanField(default=False)),
    # ❌ 不要這樣
    migrations.RunPython(lambda apps, schema_editor: upgrade_users())
]

# Good: 分開
# migration 1：加 column
migrations.AddField('user', 'premium_new', models.BooleanField(null=True))

# migration 2：data backfill（separate）
def migrate_premium(apps, schema_editor):
    User = apps.get_model('app', 'User')
    for batch in User.objects.all().values_list('id', flat=True).iterator(5000):
        User.objects.filter(id__in=batch).update(premium_new=...)
        
migrations.RunPython(migrate_premium)

# migration 3：rename
migrations.RenameField('user', 'premium', 'premium_new')
```

---

### 8.5 api-design

**觸發條件**：API 端點設計、contract 審查、分頁 / 篩選 / 排序實作

**核心內容**：
- URL 結構：複數名詞、kebab-case、無動詞、`v1` prefix
- HTTP 方法語義：GET/POST/PUT/PATCH/DELETE 冪等性與安全性
- 完整 HTTP status codes 表（2xx/3xx/4xx/5xx）
- 標準響應信封：
  - 成功集合：`{ data: [...], meta: { count, total, page }, links: { next, prev } }`
  - 單一資源：`{ data: {...} }`
  - 錯誤：`{ error: { code: "VALIDATION_ERROR", message: "...", details: [{field, message}] } }`
- Pagination：offset（簡單搜尋）vs cursor（feed）
- Filtering & Sorting：`?price[gte]=10&sort=-created_at`
- Sparse fieldsets：`?fields=id,name`
- Rate limit headers：`X-RateLimit-Limit`、`Retry-After`
- Versioning：URL path 優先，維持最多 2 版本，`Sunset` header 標記棄用
- 變更分類：breaking vs non-breaking
- Django REST Framework 例：`Serializer`、`ModelViewSet`、custom `create()`

**例子（DRF）**：
```python
# API 端點
GET /api/v1/users?page=1&per_page=20&sort=-created_at

# 響應
{
  "data": [
    {"id": 1, "name": "Alice", "email": "alice@example.com"}
  ],
  "meta": {
    "count": 1,
    "total": 100,
    "page": 1
  },
  "links": {
    "next": "/api/v1/users?page=2",
    "prev": null
  }
}

# 錯誤響應（401）
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Authentication required",
    "status": 401
  }
}
```

---

### 8.6 backend-patterns

**觸發條件**：架構設計、service layer、caching、同步 / 非同步決策

**核心內容**：
- Repository pattern：資料存取抽象（`findAll`、`findById`、`create`、`update`、`delete`）
- Service layer：業務邏輯與資料存取分離
- N+1 query 防止：batch fetch 用 Map 做 O(1) lookup
- Transaction 模式：ORM 事務或 stored procedure
- Redis caching：cache-aside pattern（get → miss → fetch → setex）
- 中央 error handler：統一例外格式
- Retry 策略：exponential backoff（1s, 2s, 4s）
- JWT 驗證 + RBAC：permissions map per role
- 速率限制：in-memory sliding window
- 簡單 job queue：processing loop（Celery for Python）
- Structured JSON logging：`requestId`、`method`、`path` context

**例子**：
```python
# Repository pattern
class UserRepository:
    def find_by_id(self, user_id):
        return User.objects.get(id=user_id)
    
    def find_all(self, limit=100, offset=0):
        return User.objects.all()[offset:offset+limit]
    
    def create(self, email, name):
        return User.objects.create(email=email, name=name)

# Service layer（業務邏輯）
class UserService:
    def __init__(self, repo, cache):
        self.repo = repo
        self.cache = cache
    
    def get_user(self, user_id):
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            return cached
        user = self.repo.find_by_id(user_id)
        self.cache.setex(f"user:{user_id}", 3600, user)
        return user
    
    def create_user(self, email, name):
        user = self.repo.create(email, name)
        return user

# API endpoint（簡單樂趣）
@app.post("/api/v1/users")
def create_user(req):
    service = UserService(repo, cache)
    user = service.create_user(req.email, req.name)
    return {"data": user}
```

---

### 8.7 docker-patterns

**觸發條件**：本地開發環境設定、containerization、debugging networking

**核心內容**：
- 標準 web stack：app + postgres + redis + mailpit（搭配 healthchecks）
- Multi-stage Dockerfile：`deps` → `dev` (hot reload) → `build` → `production` (minimal)
- `docker-compose.override.yml`（開發設定）vs `docker-compose.prod.yml`（生產）
- 服務發現：同 Compose network 內，service name = DNS
- 自訂網路：frontend-net、backend-net（隔離）
- Port binding：`127.0.0.1:5432:5432`（限制主機存取）
- Volume 策略：
  - Named volumes（持久存儲）
  - Bind mount（開發 hot reload）
  - Anonymous（保護容器目錄）
- Security：non-root user、`no-new-privileges`、`read_only: true`、`cap_drop: ALL`、`tmpfs` for /tmp
- `.dockerignore` 模板
- 機密：`.env`（gitignored）、永遠不 hardcoded

**例子（Python/Django）**：
```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ccas
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./src:/app/src  # hot reload
      - ./.venv:/app/.venv:ro  # 保護 venv
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:15
    environment:
      POSTGRES_PASSWORD: password
    healthcheck:
      test: pg_isready -U postgres
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7
    healthcheck:
      test: redis-cli ping
      interval: 10s
```

---

### 8.8 deployment-patterns

**觸發條件**：CI/CD 設定、Dockerfile 優化、health checks、生產準備

**核心內容**：
- 三種部署策略：rolling（預設，零停機）、blue-green（即時回滾）、canary（漸進切流）
- Python/Django Dockerfile：
  ```dockerfile
  FROM python:3.12-slim
  WORKDIR /app
  RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
  COPY requirements.txt .
  RUN pip install uv && uv pip install -r requirements.txt
  COPY . .
  RUN useradd -u 1001 appuser && chown -R appuser /app
  USER appuser
  ENV PYTHONUNBUFFERED=1
  CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
  ```
- Health checks：簡單 (`/health` → `{status: "ok"}`) 或詳細（含 DB/Redis/外部 API）
- GitHub Actions pipeline：test → build image → staging → production
- 健康端點模式（Django）：
  ```python
  @app.get("/health/")
  def health_check(request):
      try:
          with connection.cursor() as cursor:
              cursor.execute("SELECT 1")
          return {"status": "ok"}
      except Exception as e:
          return {"status": "error", "detail": str(e)}, 503
  ```
- Twelve-Factor App：環境變數設定，啟動時驗證
- Liveness / Readiness probes（K8s）：建議間隔
- 回滾檢查清單：前個映像可用、migration 向下相容、feature flags、監控警報

---

### 8.9 verification-loop

**已在第 3 節詳述。**

---

## 9. CCAS 專案速查表

### 9.1 任務 vs 應使用的 Command / Skill

對應 `execution-policy.md` 的觸發條件：

| 任務情境 | 應使用 | 原因 |
|---------|--------|------|
| **新功能開發** | `/plan` → `/tdd` → 實作 → `/python-review` | execution-policy "New feature" 流程 |
| **Bug fix（根因已知）** | `/tdd` → 實作 → `/python-review` | 快速路徑，無需規劃 |
| **Bug fix（根因未知）** | `bug-investigation` skill | 先找根因 |
| **SQL / Alembic 修改** | `database-migrations` skill + `database-reviewer` agent | execution-policy 強制後置 |
| **認證/輸入驗證** | `security-review` skill + `security-reviewer` agent | execution-policy 強制後置 |
| **PR 前最終驗證** | `verification-loop` skill | 6-phase 確認 |
| **旁支問題** | `/aside <question>` | 不打斷工作流 |
| **收工存檔** | `/save-session` | 為下個 session 保留上下文 |
| **下次恢復** | `/resume-session` | 快速重新進入狀態 |
| **跨專案模式** | `/instinct-status` → `/promote` | 共享最佳實踐 |

### 9.2 execution-policy 與 ECC 的對應關係

| execution-policy 規則 | ECC 實現 |
|----------------------|---------|
| 任何 Edit/Write → python-reviewer | `/python-review` (自動觸發或手動) |
| Bug fix 或新功能 → tdd-guide | `/tdd` 命令 |
| SQL / Alembic → database-reviewer | `database-migrations` skill |
| 認証/輸入驗証 → security-reviewer | `security-review` skill |

**註**：execution-policy 列出的是 **ECC agent roster**（外部 plugin 提供的代理），本指南涵蓋的 commands 是觸發這些代理的方式。

### 9.3 日常開發的標準流程（CCAS）

#### 新功能

```
1. /everything-claude-code:plan <description>
   → 使用者確認計劃

2. /everything-claude-code:tdd <feature>
   → 寫測試（RED）→ 確認失敗 → 實作（GREEN）→ 確認通過 → 重構

3. Git commit（三個 checkpoint）
   test: add test for <feature>
   fix: implement <feature>
   refactor: clean up after <feature>

4. /everything-claude-code:python-review
   → Python 審查（自動執行 mypy、ruff、bandit 等）

5. verification-loop skill（手動或自動）
   → 6-phase 確認（Build → Types → Lint → Tests → Security → Diff）

6. /everything-claude-code:save-session
   → 收工前存檔當前狀態
```

#### Bug Fix（根因已知）

```
1. /everything-claude-code:tdd <bug description>
   → 快速 RED-GREEN-REFACTOR

2. /everything-claude-code:python-review

3. verification-loop

4. /everything-claude-code:save-session
```

#### 複雜 SQL 變更

```
1. /everything-claude-code:plan <migration strategy>
   → 評估 expand-contract vs one-shot、batch 策略等

2. database-migrations skill
   → 複習遷移模式、batch 程式碼

3. 實作 migration（Django makemigrations）

4. 測試（local + staging DB）

5. database-reviewer agent（自動觸發或手動）

6. /everything-claude-code:python-review

7. /everything-claude-code:save-session
```

#### 認證相關變更

```
1. security-review skill
   → 17 點安全檢查清單

2. 實作認証 / 輸入驗証

3. security-reviewer agent（自動觸發或手動）

4. /everything-claude-code:python-review

5. /everything-claude-code:save-session
```

---

## 10. 維護與持續改進週期

### 10.1 每日

- **工作完成時**：`/save-session` 存檔
- **新 session 開始時**：`/resume-session` 恢復
- **旁支疑問**：`/aside <question>`

### 10.2 每週（每個 sprint 尾聲）

```bash
# 檢視學習成果
/everything-claude-code:instinct-status

# 清理過時 instincts
/everything-claude-code:prune

# 聚合相關 instincts 成 skills（若適用）
/everything-claude-code:evolve

# 檢查 skill 健康度
/everything-claude-code:skill-health
```

### 10.3 每月

```bash
# 匯出團隊 instincts（分享知識）
/everything-claude-code:instruct-export --min-confidence 0.8 --output team-instincts.yaml

# 審計 context 用量
/everything-claude-code:context-budget

# 評估需否更新 CLAUDE.md 或規則檔
# （若學習系統發現新模式）
```

### 10.4 季度

- 審視整體 skills 與 rules，評估是否需棄用或升級
- 與團隊同步最新 best practices（匯入隊友的 instincts）
- 更新此指南

---

## 附錄 A：命令速查

### 所有 Command 一覽

| 類別 | Command | 說明 |
|------|---------|------|
| 規劃 | `/everything-claude-code:plan` | 等使用者確認後才動手 |
| 開發 | `/everything-claude-code:tdd` | TDD 紅綠重構 |
| 審查 | `/everything-claude-code:python-review` | Python 審查 |
| 審查 | `/everything-claude-code:code-review` | 通用審查或 PR |
| 審查 | `/everything-claude-code:santa-loop` | 雙模型對抗審查 |
| 品質 | verification-loop skill | 6-phase 驗證 |
| 品質 | `/everything-claude-code:context-budget` | Context 用量審計 |
| Session | `/everything-claude-code:save-session` | 存檔 session |
| Session | `/everything-claude-code:resume-session` | 恢復 session |
| Session | `/everything-claude-code:aside` | 旁支問題 |
| 學習 | `/everything-claude-code:instinct-status` | 檢視 learned instincts |
| 學習 | `/everything-claude-code:instinct-export` | 匯出 instincts |
| 學習 | `/everything-claude-code:instinct-import` | 匯入 instincts |
| 學習 | `/everything-claude-code:evolve` | 聚合 instincts 成 skill |
| 學習 | `/everything-claude-code:promote` | 晉升跨專案 instinct |
| 學習 | `/everything-claude-code:prune` | 清理過期 instincts |
| 學習 | `/everything-claude-code:learn-eval` | 萃取 + 評估模式 |
| Skill | `/everything-claude-code:skill-create` | 從 git history 產生 skill |
| Skill | `/everything-claude-code:skill-health` | Skill 績效儀表板 |
| 多語言 | `/everything-claude-code:go-build/review/test` | Go |
| 多語言 | `/everything-claude-code:rust-build/review/test` | Rust |
| 多語言 | `/everything-claude-code:kotlin-build/review/test` | Kotlin |
| 多語言 | `/everything-claude-code:cpp-build/review/test` | C++ |

---

## 附錄 B：常見 Q&A

### Q: 何時用 `/plan` vs 直接開始？

**A**: 
- **用 `/plan`**：功能複雜、涉及多檔案、不確定最佳方案
- **不用 `/plan`**：小修復、明確需求、瑣碎變更

### Q: `/tdd` 與 `/python-review` 的順序？

**A**: `/tdd` 優先（寫測試 → 實作），完成後 `/python-review`（審查實作品質）。

### Q: Instincts 會淹沒我嗎？

**A**: 不會。系統自動 prune 30 天未審視的低信心 instincts。定期 `/evolve` 聚合相關者。

### Q: 如何分享團隊 instincts？

**A**: 
```bash
# Alice 匯出
/everything-claude-code:instinct-export --min-confidence 0.8 --output team.yaml
git commit & push

# Bob 匯入
/everything-claude-code:instinct-import https://github.com/team/repo/team.yaml --scope project
```

### Q: 何時應該用全域 vs 專案 instincts？

**A**：
- **全域**：跨專案通用（e.g., 「永遠驗證使用者輸入」）
- **專案**：CCAS 特定（e.g., 「PDF 格式總是 ROC 日期」）

### Q: 能整合既有 `.claude/rules/` 嗎？

**A**: 是的。`rules-distill` 會掃描已有 rules 並補充新發現的原則。

---

## 附錄 C：外部資源

- **ECC Plugin 目錄**：`/home/paul/.claude/plugins/marketplaces/everything-claude-code/`
- **CCAS execution-policy**：`/home/paul/projects/ccas/.claude/rules/execution-policy.md`
- **CCAS CLAUDE.md**：`/home/paul/projects/ccas/CLAUDE.md`
- **全域 CLAUDE.md**：`/home/paul/.claude/CLAUDE.md`

---

**文件版本**：1.0  
**最後更新**：2026-04-13  
**維護者**：CCAS 開發團隊  
**反饋**：請提交 issue 或 PR 至專案 repository
