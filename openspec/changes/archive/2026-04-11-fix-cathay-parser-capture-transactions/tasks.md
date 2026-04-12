## 1. TDD 前置（RED）

- [x] 1.1 挑選 4 份代表性 CATHAY PDF 從 `backend/data/staging/CATHAY/` 拷貝到 `backend/tests/integration/parser/fixtures/cathay/regression/`，覆蓋 106、108、112、115 四個年度
- [x] 1.2 新增 `backend/tests/integration/parser/test_cathay_v1_regression_capture.py`：
  - 測試 1：針對 4 份 fixture 各自 parse，`len(result.transactions) >= 1`
  - 測試 2：所有 `TransactionItem.merchant` 不含 `"帳單分期"`、`"紅利點數"`、`"優惠回饋"` 子字串
  - 測試 3：所有 `trans_date` 落在 `billing_month ± 180 天` 範圍
  - 測試 4：針對構造 text `"消費明細 01/15 星巴克 120\n帳單分期資訊\n帳單分期 12-12 33,293 2,774"` 呼叫 `_extract_transactions_text`，應回 1 筆且 merchant == `"星巴克"`
- [x] 1.3 執行 `cd backend && uv run pytest tests/integration/parser/test_cathay_v1_regression_capture.py -x` 確認 RED

## 2. 修改 `_is_transaction_table` header keyword 邏輯

- [x] 2.1 在 `cathay_v1.py` 定義 `_TRANSACTION_HEADER_DATE_KEYWORDS = ("交易日", "消費日", "日期")`、`_TRANSACTION_HEADER_AMOUNT_KEYWORDS = ("金額", "新臺幣金額", "款項")`
- [x] 2.2 `_is_transaction_table` 改為「header_text 至少命中 date 類 1 個 **且** amount 類 1 個」才回 True
- [x] 2.3 針對 `["項目", "金額"]` negative case 確認回 False
- [x] 2.4 移除或保留 `_TRANSACTION_HEADER_KEYWORDS` 常數（若不再被引用就刪）

## 3. 新增 `_crop_transaction_section` 與套用

- [x] 3.1 在 `cathay_v1.py` 新增 `_NON_TRANSACTION_SECTION_ANCHORS = ("帳單分期", "紅利點數", "優惠回饋", "本期回饋", "累積紅利", "循環信用")`
- [x] 3.2 新增 module-level helper `_crop_transaction_section(text: str) -> str`，回傳 text 切到最早 anchor 出現處之前
- [x] 3.3 在 `_extract_transactions_text` 每頁 `text = page.extract_text() or ""` 之後呼叫 `text = _crop_transaction_section(text)`
- [x] 3.4 重跑測試 1.3，應 GREEN

## 4. 手動驗收

- [ ] 4.1 `cd backend && uv run python -m ccas.pipeline --bank CATHAY --from parse --to parse` 針對 staging 107 份 PDF 全跑，記錄 `parsed_rows` 總數
- [ ] 4.2 確認總數 ≥ 500（驗收門檻）
- [ ] 4.3 `sqlite3 backend/data/ccas.db "SELECT merchant FROM transactions WHERE bank_code='CATHAY' AND merchant LIKE '%帳單分期%';"` 回傳 0 列
- [ ] 4.4 抽 3 份 PDF 人工對照，確認 parser 抓到的 merchant/amount/trans_date 與 PDF 原文一致

## 5. 回歸驗證

- [x] 5.1 `cd backend && uv run pytest tests/integration/parser/ -x`
- [x] 5.2 `cd backend && uv run pytest tests/unit/parser/ -x`
- [x] 5.3 `cd backend && uv run pytest -k cathay -x`
- [x] 5.4 在 `docs/e2e-user-guide-walkthrough.md` 問題 #6 狀態改 `archived`，`對應 change slug` 填 `fix-cathay-parser-capture-transactions`
- [x] 5.5 `openspec verify fix-cathay-parser-capture-transactions` 通過
