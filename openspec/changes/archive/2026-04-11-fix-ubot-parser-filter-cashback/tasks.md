## 1. TDD 前置（RED）

- [ ] 1.1 從 `backend/data/staging/UBOT/` 選 1 份含回饋/折抵行的 PDF 放至 `backend/tests/integration/parser/fixtures/ubot/cashback_sample.pdf`
- [ ] 1.2 新增 `backend/tests/integration/parser/test_ubot_v1_cashback_filter.py`：assert `transactions` 不含 keyword 前綴命中的 row，且所有 amount > 0
- [x] 1.3 新增 `backend/tests/unit/parser/test_ubot_is_cashback_row.py`：正例 4 筆（現金回饋、紅利折抵、負金額、`(-)` 前綴）、反例 2 筆（正常消費、商家中段含「回饋」）
- [x] 1.4 `cd backend && uv run pytest tests/integration/parser/test_ubot_v1_cashback_filter.py tests/unit/parser/test_ubot_is_cashback_row.py -x` 確認 RED

## 2. 實作 cashback filter

- [x] 2.1 在 `backend/src/ccas/parser/banks/ubot_v1.py` 新增 `_CASHBACK_KEYWORDS = ("現金回饋", "回饋入帳", "紅利折抵", "抵扣", "退款", "退貨", "沖銷")`
- [x] 2.2 新增 helper `_is_cashback_row(raw_line: str, merchant: str, amount: int) -> bool`：條件 A（前綴匹配）or B（`amount < 0`）or C（行首 `(-)` / `－`）
- [x] 2.3 主 transaction extraction 構造 `TransactionItem` 前呼叫 `_is_cashback_row` 過濾
- [x] 2.4 重跑 1.4 測試 → GREEN

## 3. 手動驗收

- [ ] 3.1 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank UBOT --from parse --to parse`
- [ ] 3.2 `sqlite3 backend/data/ccas.db "SELECT COUNT(*) FROM transactions t JOIN bills b ON t.bill_id=b.id WHERE b.bank_code='UBOT' AND (t.merchant LIKE '現金回饋%' OR t.merchant LIKE '紅利折抵%' OR t.amount < 0);"` 應回 0

## 4. 回歸驗證

- [x] 4.1 `cd backend && uv run pytest -k ubot -x`
- [x] 4.2 在 `docs/e2e-user-guide-walkthrough.md` 問題 #5 狀態改 `archived`，`對應 change slug` 填 `fix-ubot-parser-filter-cashback`
- [x] 4.3 `openspec verify fix-ubot-parser-filter-cashback` 通過
