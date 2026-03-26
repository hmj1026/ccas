---
name: git-smart-commit
description: 將 git 變更，依功能邏輯自動拆分成多個有意義的 conventional commit
---

# Git Smart Commit — 智慧拆分提交

將目前所有 staged / unstaged 變更，依功能邏輯分群後，逐批 `git add` + `git commit`。

---

## 流程

### 1. 檢查變更狀態

執行以下指令取得完整變更清單：
如果是在 wsl 環境存取 windows 的檔案，請使用 `git status --short`，不要使用 `git status --short --ignore-submodules`。

```bash
git status --short
```

若沒有任何變更，告知使用者「目前沒有需要提交的變更」後結束。

接著取得所有變更的 diff 內容（用來判斷分群邏輯）：

```bash
git diff
git diff --cached
```

---

### 2. 分析並分群

根據以下維度，將檔案變更分成多個 **commit 群組**，每組代表一個獨立的邏輯單元：

#### 分群依據（優先順序）

| 優先級 | 維度 | 範例 (符合 zdpos_dev) |
|--------|------|------|
| 1 | **專案設定 / 核心與 AI 規則** | `composer.json`, `protected/config/*`, `.gitignore`, `CLAUDE.md`, `GEMINI.md`, `*.md` 在根目錄 |
| 2 | **資料表異動 (Migration)** | `protected/migrations/*` |
| 3 | **領域邏輯 (Domain / Infra)** | `domain/*`, `infrastructure/*` |
| 4 | **MVC 架構 (Controller/Model)** | `protected/controllers/*`, `protected/models/*`, `protected/views/*` |
| 5 | **核心工具 / 共用元件** | `protected/components/*` (含 `zdnbase/*`) |
| 6 | **前端 Legacy POS** | `js/*` (例如 `zpos.js`), `css/*` |
| 7 | **自動化測試** | `protected/tests/*` |
| 8 | **文件 / 規格 (OpenSpec)** | `docs/*`, `openspec/*` |

#### 分群規則

- **領域模型與基礎設施**：同步修改的 `Domain` 與對應的 `Infrastructure` 實作應視為同一組（完整業務邏輯）。
- **MVC 功能**：同一個 Feature 的 `Controller` + `Model` + `View` 可歸為同一組。
- **資料庫遷移**：`Migration` 檔案應盡量獨立成一個 commit，方便追蹤資料庫 Schema 變更。
- **測試**：若修改某個功能，連帶修改其 `tests/*` 內的測試，應合併在同一個 commit 中。
- **其他微小變更**：若某一組只有 1 個檔案且改動極小（< 5 行），評估是否合併到最相關的鄰近組。
- **變更類型**：新增檔案用 `feat`，修改/重構用 `fix` / `refactor` / `style`，刪除或環境設定用 `chore`，文件更新用 `docs`。

---

### 3. 產出 Commit 計畫

在執行任何 git 操作之前，先列出計畫（包含預期產出的 Commit Body 摘要）讓使用者確認：

```
📋 Commit 計畫（共 N 個 commit）

1. chore(project): 更新 AI 輔助規則
   → GEMINI.md, CLAUDE.md

   同步專案最新的 PHP 5.6 限制說明與 DDD 架構規範。

2. feat(migration): 新增點數規則資料表
   → protected/migrations/m230801_120000_create_point_rule_table.php

   建立 point_rule 表，包含點數倍率、有效期限等欄位。

3. feat(domain): 實作點數計算核心領域邏輯
   → domain/Point/PointCalculator.php, infrastructure/Point/PointRepository.php

   - 實作 PointCalculator 處理倍率計算
   - 新增 PointRepository 介面與實作，支援 MySQL 讀寫

4. refactor(controller): 重構 POS 儲值控制器
   → protected/controllers/PosController.php, protected/views/pos/index.php

   將儲值邏輯從 Controller 抽離至 PointService，並優化前端 View 的回應處理。

...

確認執行？(Y/n)
```

**請暫停並等待使用者確認。**

---

### 4. 逐批執行 Commit

使用者確認後，對每一組依序執行：

```bash
git add <file1> <file2> ...
git commit -m "<type>(<scope>): <subject> <body>"
```

#### Commit Message 格式
**風格原則**：**簡短扼要，但是包含細節，且不會過長**。

```
<type>(<scope>): <簡短描述，繁體中文>

<簡短扼要且包含細節的內文，說明變更原因與重點>
```

**type 對照表：**

| type | 使用時機 |
|------|---------|
| `feat` | 新增功能、API 或頁面 |
| `fix` | 修復 bug 或異常處理 |
| `style` | 純程式碼格式或樣式調整（不影響邏輯） |
| `refactor` | 程式碼重構（不改變行為） |
| `chore` | 雜務（設定檔、相依套件更新等） |
| `docs` | 文件或註解更新 (如 `openspec/*`) |
| `test` | 新增或修改測試 |

**subject 規則：**
- 使用繁體中文
- 不超過 100 字
- 不以句號結尾
- 用「動詞開頭」：新增、調整、修正、移除、重構
- 簡短描述各別檔案的變更

**body 規則（內文）：**
- **內容重點**：說明本次變更的動機，並摘要**具體改動點**（例如：新增了哪些 method、修改了哪些關鍵邏輯、處理了什麼異常）。
- **禁止空泛描述**：不要只寫「基礎結構」、「程式碼優化」等模糊字眼，應具體說明是做了什麼樣的優化或結構。

---

### 5. 確認結果

所有 commit 完成後，執行：

```bash
git log --oneline -20
```

將結果展示給使用者，確認所有 commit 都已正確建立。

---

## 邊界情況處理

- **有衝突或 merge 狀態**：提醒使用者先解決衝突，不執行任何操作。
- **有敏感檔案**：提醒使用者確認是否應被 gitignore (例如 `.env` 或 config 內的機密寫死)，不自動提交。
- **變更量極大（> 50 個檔案）**：先產出大致的分組摘要，請使用者確認是否要更細緻拆分，確認後再執行。
- **使用者已有部分 staged 變更**：尊重已 staged 的狀態，將其視為一個獨立群組，或詢問使否要合併重新規劃。