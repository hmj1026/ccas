## 1. TDD 前置（RED）

- [ ] 1.1 從 `backend/data/staging/SINOPAC/` 選 1 份含退款行的 PDF 放至 `backend/tests/integration/parser/fixtures/sinopac/refund_sample.pdf`
- [ ] 1.2 新增 `backend/tests/integration/parser/test_sinopac_v1_refund_filter.py`：
  - 對 fixture parse 後 `transactions` 不含任一元素其 merchant 前綴命中 refund keyword
  - 所有 `amount > 0`
- [x] 1.3 新增 `backend/tests/unit/parser/test_sinopac_is_refund_row.py`：
  - 正例 3 筆（退款前綴、負金額、`(-)` 前綴）
  - 反例 3 筆（正常消費、商家中段含「退」、大額消費）
- [x] 1.4 `cd backend && uv run pytest tests/integration/parser/test_sinopac_v1_refund_filter.py tests/unit/parser/test_sinopac_is_refund_row.py -x` 確認 RED

## 2. 實作 refund filter

- [x] 2.1 在 `backend/src/ccas/parser/banks/sinopac_v1.py` 新增 `_REFUND_KEYWORDS = ("退款", "退費", "沖銷", "取消授權", "退貨")`
- [x] 2.2 新增 helper `_is_refund_row(raw_line: str, merchant: str, amount: int) -> bool`
  - 條件 A：merchant 以任一 keyword 開頭或整字等於 keyword
  - 條件 B：`amount < 0`
  - 條件 C：`raw_line.lstrip().startswith(("(-)", "－"))`
  - 回傳 `A or B or C`
- [x] 2.3 在主 transaction extraction 流程構造 `TransactionItem` 之前呼叫 `_is_refund_row` 過濾
- [x] 2.4 重跑 1.4 測試 → GREEN

## 3. 手動驗收

- [ ] 3.1 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank SINOPAC --from parse --to parse`
- [ ] 3.2 `sqlite3 backend/data/ccas.db "SELECT COUNT(*) FROM transactions t JOIN bills b ON t.bill_id=b.id WHERE b.bank_code='SINOPAC' AND (t.merchant LIKE '退款%' OR t.merchant LIKE '退費%' OR t.amount < 0);"` 應回 0

## 4. 回歸驗證

- [x] 4.1 `cd backend && uv run pytest -k sinopac -x`
- [x] 4.2 在 `docs/e2e-user-guide-walkthrough.md` 問題 #4 狀態改 `archived`，`對應 change slug` 填 `fix-sinopac-parser-filter-refunds`
- [x] 4.3 `openspec verify fix-sinopac-parser-filter-refunds` 通過
