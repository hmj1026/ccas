---
name: ccas-qa-acceptance
description: "CCAS 全端驗收測試技能（10 階段 pipeline：環境 → Docker → DB → Pipeline → 通知 → 後端測試 → API → 前端 → 額外檢查 → 報告）。支援 smoke（5-10 min）與 full（30-60 min）兩種模式。使用時機：版本發布前完整 QA 驗收、合併前全面檢查、定期品質確認、產品可用性驗證、跑完整測試流程、smoke test、驗收測試、全面驗證、問題排查後的回歸驗證。即使使用者只說「測一下」或「確認沒壞」，只要語境是全系統層級的驗證，就觸發此技能。"
---

# QA 驗收測試

10 階段端到端驗收流程，從環境配置驗證到結構化報告產出。每個階段產出 PASS/FAIL 結果與問題清單，最終彙整為可追蹤的驗收報告。

## 模式選擇

根據時間預算與驗證深度選擇模式：

| 模式 | 涵蓋 Phase | 耗時 | 適用場景 |
|------|-----------|------|---------|
| **smoke** | 0, 1, 5(unit), 6(5 critical), 7(vitest) | 5-10 min | CI/pre-merge、日常 health check |
| **full** | 0-9 全部 | 30-60 min | 版本發布、完整 QA 驗收 |

未指定時詢問使用者。若使用者說「快速檢查」選 smoke；「完整驗收」選 full。

## 錯誤分類

所有發現歸為兩類，貫穿全部 phase：

- **ERROR** — 功能性缺陷，阻塞發布。例：測試失敗、pipeline crash、API 500、migration 失敗
- **VERIFICATION-ISSUE** — 系統可運作但行為非預期，不阻塞但需追蹤。例：某銀行交易數偏低、回應時間超過基準、warning 日誌異常

每個發現記錄格式：`[Phase.Step] [ERROR|VERIFICATION-ISSUE] 描述`

## 並行策略

Phase 0-3 必須依序執行（各依賴前一階段結果）。之後可並行：

```
Phase 0 → Phase 1 → Phase 2 → Phase 3
                                  ↓
                    ┌─────────────┼─────────────┐
                    ↓             ↓             ↓
              Phase 4+5      Phase 6+7      Phase 8
              (測試套件)     (API+前端)     (額外檢查)
                    └─────────────┼─────────────┘
                                  ↓
                              Phase 9
                             (報告統整)
```

## Phase 0: 環境與憑證驗證

驗證執行 QA 所需的所有前置條件，避免在後續階段才發現基礎配置問題。

執行 bundled script：
```bash
bash .agents/skills/ccas-qa-acceptance/scripts/qa-env-check.sh [--mode smoke|full]
```

檢查項目：
- `.env` 必要變數（透過既有 `scripts/check-env.sh`）
- Docker Engine 與 Compose 版本
- `config/banks.yaml`、`config/categories.yaml`、`config/bank-code-registry.yaml` 存在
- Gmail OAuth credentials/token 存在（依 `.env` 路徑）
- 各銀行 `PDF_PASSWORD_<CODE>` 設定（缺少 → VERIFICATION-ISSUE）
- Port 8000/5173/6379 可用性
- 磁碟空間 >= 2GB

**失敗處理**：必要變數缺失 → ERROR，立即停止。可選項缺失 → VERIFICATION-ISSUE，繼續。

## Phase 1: Docker 基礎建設

確保所有容器服務正常運行，為後續階段提供穩定的執行環境。

```bash
# 判斷是否需要重建（比較映像時間與 Dockerfile/lock 檔異動）
docker compose images 2>/dev/null
git log -1 --format="%H %ci" -- backend/Dockerfile backend/pyproject.toml backend/uv.lock
git log -1 --format="%H %ci" -- frontend/Dockerfile frontend/package.json frontend/pnpm-lock.yaml

# 建構（如需要）並啟動
docker compose build    # 僅在映像過期時
docker compose up -d

# 等待健康檢查
timeout 120 bash -c 'until curl -sf http://127.0.0.1:8000/health; do sleep 2; done'
docker compose exec redis redis-cli ping
timeout 60 bash -c 'until curl -sf http://127.0.0.1:5173/ > /dev/null 2>&1; do sleep 2; done'
```

驗證：6 服務 running（`docker compose ps`）、backend health OK、Redis PONG、前端可存取。

**失敗處理**：任一服務啟動失敗 → ERROR，停止。檢查 `docker compose logs <service>` 排查。

## Phase 2: 資料庫重置

QA 需要乾淨的 DB 讓 pipeline 填入真實資料。使用 alembic 重建 schema，不用 `seed.py --reset`（後者會插入範例資料，污染驗收結果）。

執行 bundled script：
```bash
bash .agents/skills/ccas-qa-acceptance/scripts/qa-db-reset.sh [--verify-only]
```

流程：alembic downgrade base → upgrade head → seed bank_configs（7 銀行） → seed categories

驗證：
- `bank_configs` = 7（CTBC, SINOPAC, ESUN, TAISHIN, UBOT, CATHAY, FUBON）
- `categories` > 0
- `bills` = 0, `transactions` = 0（乾淨狀態）
- WAL mode active

**失敗處理**：migration 失敗 → ERROR。嘗試 `docker compose down -v && docker compose up -d` 後重試。

## Phase 3: Pipeline 全銀行執行

Pipeline 透過 `docker compose exec` 執行，因為 staging 目錄由 Docker root 建立，本機 user 無寫入權限。使用 `--to classify` 跳過 notify（Phase 4 單獨驗證通知邏輯）。

執行 bundled script：
```bash
bash .agents/skills/ccas-qa-acceptance/scripts/qa-pipeline-run.sh [--bank BANK] [--snapshot-dir DIR]
```

流程：
1. 從 `config/banks.yaml` 讀取 active banks
2. 逐銀行執行 `docker compose exec backend uv run python -m ccas.pipeline --bank $BANK --to classify --force`
3. 記錄每銀行耗時
4. 擷取 DB snapshot（各銀行 bills/transactions 數量、總金額）
5. 資料完整性交叉比對：`bill.total_amount` vs `SUM(transactions.amount)`

驗證：pipeline exit 0、每家銀行至少產出 1 筆 bill、snapshot 儲存成功。

**失敗處理**：單一銀行失敗 → VERIFICATION-ISSUE，記錄後繼續其餘銀行。全部失敗 → ERROR。

## Phase 4: Telegram 通知邏輯驗證

TG token 未設定不影響測試。驗證的是程式邏輯：token 為空時應自動跳過，不 crash。

```bash
# 通知相關 unit tests
./scripts/dev-test.sh tests/unit/bot/ -v

# 驗證 skip 邏輯
docker compose exec backend uv run python -m ccas.pipeline --from notify --to notify
# 預期日誌：「跳過 notify stage」，sent=0, failed=0
```

驗證：所有 bot tests PASS、notify stage 正確跳過。

## Phase 5: 後端測試套件

```bash
./scripts/dev-test.sh tests/unit/ -v --tb=short
./scripts/dev-test.sh tests/integration/ -v --tb=short
./scripts/dev-test.sh tests/e2e/ -v --tb=short
./scripts/dev-test.sh --cov --cov-report=term-missing   # coverage >= 80%
```

smoke 模式僅跑 unit tests。

驗證：all PASS、coverage >= 80%。日誌保存到 `test-results/qa-pytest-output.txt`。

**失敗處理**：測試失敗 → ERROR。記錄失敗清單，繼續後續 phase。

## Phase 6: API 端點驗證

共 26 端點，自動化驗證 HTTP status、response body、安全標頭、回應時間。

執行 bundled script：
```bash
bash .agents/skills/ccas-qa-acceptance/scripts/qa-api-verify.sh [--base-url URL] [--mode smoke|full]
```

smoke 模式驗證 5 個 critical endpoints：`/health`、`POST /api/auth/session`、`GET /api/overview`、`GET /api/bills`、`GET /api/transactions`。

full 模式驗證全部 26 端點，包含：
- Auth flow（login/logout/session check）
- CRUD operations（categories create/read/update/delete）
- Pagination（bills, transactions, staged-attachments）
- Export（CSV download）
- 401 unauthorized 驗證
- Security headers（X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP）
- 資料一致性：overview.total_spending vs bills 加總

端點完整清單見 `references/api-endpoints.md`。

## Phase 7: 前端測試與視覺驗證

```bash
# Vitest unit tests
cd frontend && pnpm test

# Playwright E2E
cd frontend && API_TOKEN=$(grep '^API_TOKEN=' ../.env | cut -d= -f2) pnpm e2e
```

smoke 模式僅跑 Vitest。full 模式加跑 Playwright E2E（auth + pages specs）。

視覺驗證（full 模式，透過 playwright-cli 或 agent-browser）：
- Overview: total_spending/paid/unpaid 與 API 一致
- Bills: 帳單筆數與 DB 一致
- Transactions: 交易筆數與 DB 一致，篩選器正常
- Analytics: 圖表有渲染
- Settings: 7 銀行顯示正確

## Phase 8: 額外 QA 檢查點

系統層面的非功能性驗證，捕捉 Phase 4-7 未涵蓋的問題：

1. **WAL mode**：`PRAGMA journal_mode` = `wal`
2. **Pipeline trigger via API**：`POST /api/pipeline/trigger` 驗證 RQ job 入隊
3. **Cascade delete**：刪除 bill 後 transactions 自動清除
4. **Redis 連線**：worker/scheduler 正常連接
5. **Security headers**：nginx 端（port 8080）逐一驗證
6. **DB constraints**：unique constraint on `bank_configs(bank_code)`、FK integrity
7. **Session 過期**：cookie max-age 設定正確
8. **日誌收集**：`docker compose logs --no-color > test-results/qa-docker-logs.txt`

## Phase 9: 報告產出

執行 bundled script：
```bash
bash .agents/skills/ccas-qa-acceptance/scripts/qa-report.sh [--output DIR]
```

產出 `.reports/qa-acceptance-YYYY-MM-DD-HHmm.md`，格式見 `references/report-template.md`。

報告包含：
- 各 Phase 狀態（PASS/FAIL）
- 問題清單（ERROR / VERIFICATION-ISSUE），每項含 Phase、描述、分類
- 效能基準（pipeline 耗時、測試時間）
- 回歸分析（與前次報告比對：新增/已解決/持續問題）
- 後續行動建議

效能基準存入 `.reports/qa-baselines.json` 供未來回歸比對。

## 錯誤恢復

| Phase | 失敗時處理 |
|-------|-----------|
| 0-1 | 立即停止。環境/基礎設施不正確，後續階段無意義 |
| 2 | 嘗試 `docker compose down -v && docker compose up -d` 後重試 |
| 3 | 記錄失敗銀行，跳到 Phase 5（測試不依賴 pipeline 資料） |
| 4-8 | 記錄 ERROR 後繼續下一 phase。這些階段彼此獨立 |
| 9 | 始終執行。即使前面有失敗，仍產出報告記錄所有發現 |

## 回滾/清理

QA 完成後恢復環境：

```bash
# 保留資料，僅停止服務
docker compose down

# 完全重置（含 volumes）
docker compose down -v

# 清理測試產物
rm -rf test-results/ frontend/playwright-report/ frontend/test-results/
```

## 驗證清單

- [ ] Phase 0-9 全部執行完畢
- [ ] 所有 ERROR 等級問題已記錄
- [ ] 報告已產出到 `.reports/`
- [ ] 效能基準已更新
- [ ] 問題清單已產出供後續行動使用

## Bundled Resources

| 資源 | 用途 | 載入時機 |
|------|------|---------|
| `scripts/qa-env-check.sh` | Phase 0 環境檢查 | Phase 0 執行時 |
| `scripts/qa-db-reset.sh` | Phase 2 DB 重置與驗證 | Phase 2 執行時 |
| `scripts/qa-pipeline-run.sh` | Phase 3 pipeline + snapshot | Phase 3 執行時 |
| `scripts/qa-api-verify.sh` | Phase 6 API 端點驗證 | Phase 6 執行時 |
| `scripts/qa-report.sh` | Phase 9 報告產出 | Phase 9 執行時 |
| `references/api-endpoints.md` | 26 端點驗證清單 | Phase 6 需查閱端點細節時 |
| `references/report-template.md` | 報告 markdown 模板 | Phase 9 產出報告時 |
