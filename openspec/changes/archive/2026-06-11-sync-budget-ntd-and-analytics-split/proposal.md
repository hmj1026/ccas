## Why

全面品質稽核確認系統實際以 NTD 整數「元」儲存所有金額（不乘 100），但 `budgets` / `budget_alerts` 的 `*_minor_units` 欄位命名與主規格「金額以分儲存」的敘述互相矛盾，會誘導未來開發者引入 ×100 錯誤；同時 `GET /api/analytics/categories` 的 union 回應形狀（`compare_with_previous` 參數切換兩種 schema）對前端 codegen 不友善且違反 `python-api.md` 的單一 `response_model` 慣例。兩項改善已實作完成且測試全綠，本變更補上正規 artifacts 並同步主規格。

## What Changes

- **BREAKING** `budgets.amount_minor_units` → `amount_ntd`、`budget_alerts.current_amount_minor_units` → `current_amount_ntd`（Alembic migration `f3a9d8c1b2e4`，僅改名不轉換數值）；API 欄位名與前端型別同步更名
- 規格中「金額以分儲存」的敘述更正為「NTD 整數元，全系統不做單位換算」
- **BREAKING** `GET /api/analytics/categories` 移除 `compare_with_previous` 參數，固定回傳 `ApiResponse[list[CategoryItem]]`
- 新增 `GET /api/analytics/categories/compare`（`month` 必填，缺少回 422），回傳 `ApiResponse[list[CategoryWithCompareItem]]`（含 `previous_amount` 與 `change_percent`）
- analytics 各端點回應的金額欄位單位敘述統一為 NTD 元

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `budget-and-overspend-alerts`: 金額欄位改名為 `amount_ntd` / `current_amount_ntd`，單位語意由「分」更正為「NTD 整數元」
- `insights-dashboard-v2`: categories 端點拆分為基礎端點與 `/compare` 端點；金額欄位單位敘述更正為 NTD 元

## Impact

- 後端：`storage/models.py`、`api/routers/budgets.py`、`api/routers/analytics.py`、`api/schemas.py`、`scheduler/budget_evaluator.py`、migration `f3a9d8c1b2e4`
- 前端：`lib/types.ts`、`pages/settings-budgets.tsx`、`pages/insights.tsx`、`components/budget-alert-banner.tsx`、`components/budget-progress-card.tsx`
- API 消費者：欄位名與端點路徑屬 breaking change（前後端同 repo 已同步；無已知外部消費者）
- 文件：`.claude/rules/python-db.md`、`.claude/rules/parser-development.md`、`docs/personal-rules-and-budgets.md`、`docs/CODEMAPS/data.md` 已同步更正
