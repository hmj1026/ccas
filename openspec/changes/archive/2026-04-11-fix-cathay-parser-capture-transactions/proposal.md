## Why

E2E walkthrough 問題 #6：CATHAY 107 份帳單 PDF 經 pipeline 解析後，`ParseResult.transactions` 總筆數只抓到 **90 筆**，遠低於合理值（107 期帳單 × 多筆消費應有數百到上千筆）；且實際被捕捉的 row 內容型如：

```
帳單分期 12-12 33,293 2,774 6.00%
```

這**不是**真正的消費交易，而是帳單後段「本期分期資訊」或「紅利/回饋說明」欄位被 regex 誤認。真正的消費明細行（日期 + 商店名 + 金額）完全沒進到 `TransactionItem`。

根因候選（待 TDD RED fixture 實測）：

1. **表格擷取路徑（`_extract_transactions_table`）**：`_is_transaction_table` 只檢查 header 含「交易日」+「金額」，但 CATHAY 實際 PDF 的交易明細表可能 header 欄位名不同（例如「消費日」、「入帳日」、「款項」等），導致表格擷取永遠 miss；fallback 走到 text 路徑。
2. **文字擷取路徑（`_extract_transactions_text`）**：`_RE_TRANSACTION_LINE`（日期 日期 商家 金額）與 `_RE_TRANSACTION_LINE_SIMPLE`（日期 商家 金額）對真正消費行 match 失敗，卻湊巧 match 到「帳單分期」區塊的行尾數字組合（`12-12` 被當成日期？還是金額欄位 `33,293` 配合前面文字被吃掉？），產出無意義 row。
3. **billing_year 推導**：若 `_extract_billing_month` 回傳 `None`，所有交易行會走 fallback year，可能造成 `_parse_date` 拋錯後被 warn+skip。

後果：使用者在前端 `/transactions?bank_code=CATHAY` 看不到任何實際消費紀錄，`/bills` 列表雖然有 bill 但 `transaction_count` 永遠 < 1；整體 CATHAY 部分的 pipeline 等同不可用。

## What Changes

- **修改 `backend/src/ccas/parser/banks/cathay_v1.py`** 的交易擷取邏輯：
  - 擴充 `_TRANSACTION_HEADER_KEYWORDS`（或改採 keyword set 任一命中）以涵蓋 CATHAY 實際 header 用字（具體值待 TDD fixture 決定）。
  - 調整 `_RE_TRANSACTION_LINE` / `_RE_TRANSACTION_LINE_SIMPLE` 讓其**只**匹配真正消費行（日期在行首 + 金額在行尾）；確認「帳單分期」、「紅利回饋」等段落不被誤吃。
  - 新增一個 section-filter：`_extract_transactions_text` 跑 regex 前，先把「帳單分期資訊」、「紅利點數」、「優惠回饋」等非交易段落**截掉**再掃描（以 `re.split` + section header anchor 完成）。
- **新增真實 PDF fixture**：至少 2 份不同期別的 CATHAY 解密後 PDF（由 `backend/data/staging/CATHAY/*.pdf` 挑選）放入 `backend/tests/integration/parser/fixtures/cathay/`（使用脫敏 fixture 或直接 reference staging path by marker），於 `test_cathay_v1_pdf.py` 新增 failing case。
- **新增 regression unit test**：確認「帳單分期」區段不被誤判為交易（`_extract_transactions_text` 對包含分期段落的 text 應回傳 0 筆 installment row）。

**非範圍**：
- 不改 classifier 對 CATHAY 分類規則（屬於另一個 change #3）。
- 不改 `billing_month` / `due_date` / `total_amount` 擷取邏輯（既有 spec 已驗證通過）。
- 不動 parser registry、bank_parser_contract 介面。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `cathay-parser`：**修正**「parse 提取交易明細」需求，強化規範「必須只擷取真正消費交易、排除分期資訊與紅利回饋等非交易段落」，並補上「表格 header keyword 必須涵蓋 CATHAY 實際用字」的 scenario。

## Impact

- **程式**：`backend/src/ccas/parser/banks/cathay_v1.py`
- **測試**：`backend/tests/integration/parser/test_cathay_v1_pdf.py`、`backend/tests/integration/parser/test_cathay_parse_job.py`（可能補 regression），以及新增 fixtures。
- **相容性**：介面與回傳 schema 完全不變；既有上游（orchestrator、classifier、API）不受影響。
- **資料遷移**：已 parse 過的 CATHAY bill 在 DB 中 transactions 空或錯誤，修完後需重跑 `pipeline --bank CATHAY --from parse --to classify` 做一次回填；此操作由使用者手動觸發，不在本 change 腳本化。
- **風險**：若 regex 收緊不當，可能漏抓少數非典型 row；由 TDD fixture 覆蓋多期 PDF 緩解。
