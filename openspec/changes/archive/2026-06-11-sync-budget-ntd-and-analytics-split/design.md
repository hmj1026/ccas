## Context

全面品質稽核（2026-06）發現兩處規格與實作矛盾：(1) `budgets` / `budget_alerts` 欄位以 `*_minor_units` 命名且規格寫「以分儲存」，但全系統（parser → storage → API → 前端）實際一律以 NTD 整數元儲存、從未乘 100——命名與文件會誘導未來開發者引入 ×100 錯誤；(2) `GET /api/analytics/categories` 以 `compare_with_previous` 參數切換兩種 response schema，違反 `python-api.md` 的固定 `response_model` 慣例。本變更為「實作先行、規格補同步」：程式碼已完成並通過全部測試，此處補上正規 artifacts 供 `/opsx:sync` 同步主規格。

## Goals / Non-Goals

**Goals:**
- 主規格與實際程式碼一致：欄位名 `amount_ntd` / `current_amount_ntd`、單位語意「NTD 整數元，不做單位換算」
- analytics categories 拆分為兩個固定 schema 的端點並反映實際 response 欄位名（`total` / `previous_total` / `change_percent`）
- `compare/banks`、`top-merchants` 的 response 形狀同步為實際欄位名

**Non-Goals:**
- 不改為「以分儲存」方案（NTD 無小數需求，全面轉換破壞面過大且無收益）
- 不處理規格中其他既有漂移（如 `id` UUID PK vs 實際 int PK）——留待獨立的規格盤點變更
- 不新增任何執行期行為

## Decisions

- **改名而非改值**：migration `f3a9d8c1b2e4` 以 `batch_alter_table` RENAME COLUMN，資料值不動（值本來就是元）。對比方案「全系統改存分」需改 parser/classifier/insights/前端全鏈路且無實際需求。
- **拆端點而非 union schema**：`/categories/compare` 獨立端點 + `month` 必填，OpenAPI 對 codegen 友善；對比方案「保留參數 + anyOf response」前端型別推導困難。
- **delta spec 同步 `compare/banks` / `top-merchants` 實際欄位名**：規格原寫 `amount_minor_units` / `total_amount_minor_units`，實作從未使用該命名；既然本變更主旨即金額欄位語意修正，一併同步避免留下半套。

## Risks / Trade-offs

- [API breaking change：欄位名與端點參數變更] → 前後端同 repo 已同步更名；無已知外部消費者；若未來有外部整合需在 release note 標注
- [migration 在 SQLite 上 RENAME COLUMN] → 已用 alembic batch 模式並有 up/down/up 測試（`test_budget_amount_ntd_migration.py`）
- [規格其他漂移仍存在] → 已在 Non-Goals 明示，避免誤以為本變更後規格與實作完全一致

## Migration Plan

已完成：migration `f3a9d8c1b2e4`（升級時自動執行 `alembic upgrade head`）；downgrade 完整可逆。規格同步：`/opsx:sync` 將本 change 的 delta specs 套入 `openspec/specs/`。

## Open Questions

（無）
