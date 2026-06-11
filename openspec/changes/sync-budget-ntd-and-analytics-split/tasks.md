> 注：本變更為「實作先行、規格補同步」——以下任務在 change 建立前已全部完成並通過測試（後端 pytest 1541 passed、前端 vitest/tsc/eslint 全綠），勾選狀態反映既成事實。

## 1. Budget 金額欄位改名（amount_ntd）

- [x] 1.1 Alembic migration `f3a9d8c1b2e4`：`budgets.amount_minor_units` → `amount_ntd`、`budget_alerts.current_amount_minor_units` → `current_amount_ntd`（batch_alter_table，downgrade 完整可逆）
- [x] 1.2 `storage/models.py`、`api/schemas.py`、`api/routers/budgets.py`、`scheduler/budget_evaluator.py` 同步更名
- [x] 1.3 前端 `lib/types.ts`、`pages/settings-budgets.tsx`、`components/budget-alert-banner.tsx`、`components/budget-progress-card.tsx` 同步更名
- [x] 1.4 migration up/down/up 測試（`tests/unit/storage/test_budget_amount_ntd_migration.py`）
- [x] 1.5 更新所有引用測試（backend `-k "budget or migration"` 43 passed、frontend settings-budgets 9 passed）

## 2. 金額單位文件修正（NTD 整數元 SSOT）

- [x] 2.1 `.claude/rules/python-db.md`、`.claude/rules/parser-development.md`：統一為「全系統以 NTD 整數元儲存，不乘 100」，刪除與程式碼矛盾的敘述
- [x] 2.2 `docs/personal-rules-and-budgets.md`（含 curl 範例）、`docs/CODEMAPS/data.md` 欄位名與單位敘述更正
- [x] 2.3 對照 `parser/result.py`、`parser/staging.py` 驗證「無 ×100 轉換」屬實（doc-reviewer 確認）

## 3. Analytics categories 端點拆分

- [x] 3.1 `api/routers/analytics.py`：`GET /categories` 移除 `compare_with_previous`，固定 `ApiResponse[list[CategoryItem]]`
- [x] 3.2 新增 `GET /categories/compare`（`month` 必填 YYYY-MM，缺少回 422），回 `ApiResponse[list[CategoryWithCompareItem]]`
- [x] 3.3 `api/schemas.py` 明確定義兩個 response item schema
- [x] 3.4 前端 `pages/insights.tsx` 呼叫端與測試 mock 改用 `/categories/compare`
- [x] 3.5 整合測試 URL 同步更新（`-k analytics` 通過）

## 4. 規格同步

- [x] 4.1 撰寫 delta specs（`budget-and-overspend-alerts`、`insights-dashboard-v2`）
- [x] 4.2 `/opsx:sync` 套用 delta 至 `openspec/specs/`
- [ ] 4.3 `/opsx:archive` 歸檔本變更
