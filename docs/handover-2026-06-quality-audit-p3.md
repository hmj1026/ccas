# 交接文件 — 2026-06 品質稽核 P3 Backlog

> 用途：P1+P2 已修復並提交（見下方 commit 群）。本文件供**新對話**接續處理 **P3（9 項）**。
> 來源：`ccas-quality-audit`（8 維度 + 對抗式驗證，76 子代理）。原始稽核結果與完整路線圖見該次執行輸出。

## 背景脈絡

- 全專案 8 維度品質皆 7–7.5/10；無循環匯入、無立即安全漏洞、無資料損毀型缺陷。
- 稽核 64 項發現 → **41 真實缺陷 / 12 純防禦 / 11 假陽性**，去重成 16 項路線圖。
- **P1（2）+ P2（5）+ 1 跨階段回歸已全數修復**，全套件 **1692 passed**、ruff + pyright strict 0 errors。
- 12 項純防禦性已記錄於 auto-memory `defensive_only_findings.md`（每 session 自動載入）——**勿再列入待修**。

## 已完成（P1+P2，本批 commit）

| 級別 | 項目 | 關鍵檔案 |
|---|---|---|
| P1 | classify 整批 commit 失敗誤標 SUCCEEDED + 資料遺失 | pipeline/worker.py |
| P1 | CTBC labeled 格式跨年交易年份錯誤 | parser/banks/ctbc_v1.py |
| P2 | 安全硬化（Telegram 空名單告警 / redis-commander Basic Auth / Dockerfile --frozen） | bot/app.py, docker-compose.yaml, Dockerfile, .env.example |
| P2 | HTTPException 統一 ApiResponse 信封 | api/app.py, frontend api-client.ts |
| P2 | 通知可靠性（BudgetAlert.notified 補推 + Gmail 逐封失敗隔離） | scheduler/budget_evaluator.py, storage/models.py, ingestor/gmail_client.py, migration 413739f494ff |
| P2 | staged 重試殘留 + UBOT/SINOPAC 解析韌性 | ingestor/job.py, parser/banks/ubot_v1.py, sinopac_v1.py |
| P2 | Category FK 完整性 + 測試缺口補強 | storage/database.py(`foreign_keys=ON`), api/routers/settings.py |
| 跨階段 | delete_budget 在 FK ON 下級聯清 BudgetAlert（避免 500） | api/routers/budgets.py |

> ⚠️ 重要副作用提醒：`storage/database.py` 已開啟 SQLite `PRAGMA foreign_keys=ON`。**任何新增的 delete 路由都必須處理子表 FK**（級聯清除或回 409）。現存 delete 路由已全部稽核過（category→409、budget→級聯、其餘無子表或已 cascade）。

---

## P3 進度

| 項目 | 狀態 | Commit |
|---|---|---|
| P3-8 REDIS_PASSWORD https prod 阻斷 | ✅ 已完成 | `7fdca20` |
| P3-3 CSP SSOT 比對 + parser 動態探索 | ✅ 已完成 | `34fa532` |
| P3-2 通知呼叫端統一 bot.notifications | ✅ 已完成 | `17b9745` |
| P3-1 stage→pipeline 層解耦（建 ccas.shared） | ✅ 已完成 | （本批） |
| P3-4 / P3-5 / P3-6 / P3-7 | ⬜ 待辦 | — |

> P3-2 已順帶解決 `defensive_only_findings.md` #2（render_due_reminder 接 Bill ORM 不一致）——該項已改純量、不再是「純防禦勿修」。

## P3 Backlog（待辦，建議獨立 PR 逐項處理）

> 工作量：S=小 / M=中 / L=大。每項修改前依專案規則跑 `gitnexus_impact`，遵循 TDD，最後過 reviewer。
>
> **路徑慣例**：以下後端檔案路徑相對於 `backend/src/ccas/`（如 `parser/banks/ctbc_v1.py` =
> `backend/src/ccas/parser/banks/ctbc_v1.py`）；前端相對於 `frontend/src/`；其餘（scripts/、
> docs/、.claude/）為 repo 根目錄相對路徑。測試檔給完整 repo 相對路徑。

### P3-1 stage 模組向上依賴 pipeline 協調層解耦（架構，M） — ✅ 已完成
- **檔案**：ingestor/job.py, parser/job.py, parser/staging.py, decryptor/job.py, decryptor/staging.py, classifier/job.py, bot/job.py
- **做法**：建 `ccas.shared.progress`（ProgressReporter Protocol + Noop）與 `ccas.shared.pipeline_types`（PipelineOptions）；`ccas.pipeline.progress/options` re-export 維持相容；`apply_pipeline_filters` 移至 `ccas.shared.filters`（依賴方向 shared→storage）；stage import 全改 shared。DbProgressReporter 留 pipeline 層。
- **實作結果**：新增 `ccas/shared/{__init__,pipeline_types,progress,filters}.py`（各帶 `__all__`）；pipeline 三檔轉純 re-export shim；7 個 stage 檔改 import；新增 `tests/unit/shared/test_layering.py`（AST 層界守門 + re-export 同一物件 `is` 斷言）；`test_options.py` patch 目標跟進 `ccas.shared.pipeline_types.date`。全套件 1703 passed、ruff + pyright strict 0 errors、python-reviewer APPROVE。
- **殘留（非本次範疇）**：`bot/job.py` 仍 import `ccas.pipeline.summary.NotifySummary`——該值型別刻意置於 pipeline 層以打破 pipeline→bot 反向相依（見 `pipeline/summary.py` docstring），屬已定案設計。若日後要徹底解耦 bot，可評估將 summary 值型別一併下移 shared。

### P3-2 三處通知呼叫端統一改用 bot.notifications 高階層（架構，S） — ✅ 已完成（`17b9745`）
- **檔案**：api/routers/reminders_settings.py, scheduler/reminders.py, bot/job.py
- **做法**：bot/notifications.py 已有 notify_due_reminder/notify_new_bill/notify_parse_failure 但無呼叫端使用。三處改用之，移除散落的 render+send_message。
- **風險**：notify_new_bill 接受 Bill ORM 物件，job.py 已萃取純量避 MissingGreenlet——須先確認簽章相容（見 defensive_only_findings #2）。

### P3-3 CSP SSOT 整合 + bank parser 動態探索（架構，S） — ✅ 已完成（`34fa532`）
- **檔案**：api/app.py, `frontend/nginx.conf`, parser/banks/__init__.py, `.claude/rules/parser-development.md`
- **做法**：(a) CSP 真實重複點為 api/app.py 與 frontend/nginx.conf；最低風險＝新增 CI 腳本 grep 比對兩者一致（仿 `scripts/check-env-sync.sh`）。(b) banks/__init__.py 改 pkgutil.iter_modules + `^[a-z]+_v\d+$` 過濾自動載入，刪 `.claude/rules/parser-development.md` 步驟 5。
- **風險**：動態探索須加測試斷言 registry 含全部 7 家 parser，避免漏載。

### P3-4 效能預防性優化（效能，M）
- **檔案**：api/routers/overview.py, classifier/engine.py, api/routers/transactions.py, ingestor/retry.py, frontend/vite.config.ts
- **做法**：(1) overview 摘要改 SQL 聚合(coalesce+sum+case)。(2) engine classify 外層快取 best_len 消除重複 normalize。(3) transactions q 參數 min_length=2。(4) retry.py 最後一次重試前略過 sleep。(5) vite manualChunks 加 query/router/ui。
- **風險**：overview 改寫須確認空月份回 0 測試；q min_length 須確認前端未送單字元；retry sleep 次數變動須同步測試斷言。

### P3-5 API 一致性批次（易用性，M）
- **檔案**：api/routers/analytics_v2.py, api/routers/transactions.py, api/routers/transactions_edit.py, api/app.py, api/routers/setup/gmail.py, `README.md`, `README.zh-TW.md`, `docs/install-quickstart.md`
- **做法**：(1) analytics_v2 tag 改 ['analytics']。(2) transactions/transactions_edit prefix 由裸 '/api' 改 '/api/transactions'。(3) app.py 加 /api/health/ready 別名。(4) transactions PUT→PATCH（前後端同步）。(5) gmail callback 取 userinfo email。(6) README curl 加 REPO_OWNER。
- **風險**：prefix 改名 + PUT→PATCH 須前後端同步否則 405；gmail userinfo 多一次外部 HTTP 須 timeout + 失敗不阻斷。

### P3-6 前端設計系統與無障礙一致性（UI/UX，L）★最大
- **檔案**（皆相對於 `frontend/src/`）：components/shared/filter-bar.tsx, pages/transactions.tsx, pages/insights.tsx, pages/setup/admin.tsx, pages/settings-budgets.tsx, pages/settings-rules.tsx, pages/settings-reminders.tsx, components/staged-attachments-warning.tsx, components/budget-alert-banner.tsx, pages/bills.tsx, lib/utils.ts（實際路徑以稽核結果為準，必要時用 `cx`/grep 定位）
- **做法**：建 SelectField wrapper 收斂 17 處原生 select（待 `shadcn add select`）；交易列商家名改 Link 提升鍵盤可達；類別比較區段未選月顯示 EmptyState；admin toLocaleString 加 'zh-TW'；表單補 htmlFor/id；展開區加 aria-controls；分頁守門統一。
- **風險**：select 遷移 17 處範圍大、須逐頁回歸；Playwright e2e 若依賴原生 select DOM 須同步。**建議拆多個小 PR**。

### P3-7 FUBON 登入憑證加密儲存（安全，M）
- **檔案**：config.py, ingestor/job.py, storage/models.py, api/routers/setup/（目錄）
- **做法**：FUBON_NATIONAL_ID/FUBON_ROC_BIRTHDAY 目前 env 明文。新增 BankLoginCredential 表(複合主鍵, Fernet 加密)，擴充掃描支援 {BANK}_{KEY}，get_bank_credential 優先查 DB、env 作 legacy fallback。勿混入既有 bank_secrets 表。
- **風險**：新表需 migration + setup UI；屬架構完整性非即時漏洞（log RedactingFilter 已遮蔽），可排靠後。

### P3-8 REDIS_PASSWORD 空值在 prod 升級為阻斷（安全，S） — ✅ 已完成（`7fdca20`）
- **檔案**：scripts/check-env.sh, .env.example
- **做法**：check-env.sh 若 PUBLIC_BASE_URL 為 https:// 且 REDIS_PASSWORD 空，升級為 format_errors（阻斷），與 API_COOKIE_SECURE 條件式阻斷一致；dev(http) 維持 WARN。
- **風險**：升級阻斷可能影響誤用 https 但故意不設密碼的部署（預期應阻斷）。

> P3-9 原為 CTBC ROC 跨年測試缺口，已併入 P1（同根因，ROC 路徑實際不受影響）；不需再處理。

---

## 開發指令速查

```bash
./scripts/dev-test.sh                 # 全測試（in-memory SQLite，免 Docker）
./scripts/dev-test.sh tests/unit/ -v  # 單元
./scripts/dev-lint.sh                 # ruff check + format + pyright(strict)
cd backend && uv run alembic upgrade head
```

## 慣例提醒
- 回應繁中；branch/change 名 kebab-case；金額全程 NTD 整數元（不乘 100）。
- 改 symbol 前 `gitnexus_impact`；提交前 `gitnexus_detect_changes`；rename 用 `gitnexus_rename`。
- 改 SSOT（.env.example/check-env.sh/docker-entrypoint.sh）後跑 `./scripts/sync-docker-image-assets.sh` 並 stage mirror。
- 強制 post-step（依 `.claude/rules/execution-policy.md` Mandatory Post-steps，順序如下）：bug/feature 先 `dhpk:tdd-guide`；SQL/Alembic→`dhpk:database-reviewer`；auth/輸入驗證/secrets→`dhpk:security-reviewer`；任何 Edit/Write 最後一步→`python-reviewer`(ECC)。`dhpk:code-reviewer` 為建議的最終整體把關（非 execution-policy 強制表列，但 sentinel 流程會提醒）。
