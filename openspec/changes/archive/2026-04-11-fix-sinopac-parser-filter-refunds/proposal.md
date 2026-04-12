## Why

E2E walkthrough 問題 #4：SINOPAC parser 將帳單末段的「退款/退費/沖銷」行與正常消費行混在同一個 `transactions` 列表裡寫入 DB，導致：

- `/api/transactions?bank_code=SINOPAC` 的金額統計與 `bills.total_amount` 對不上（退款負值被當成正值消費）
- classifier 把退款 row 當新消費分類
- 前端 `/analytics` 月度消費圖表 SINOPAC 欄位虛高

查看 `backend/src/ccas/parser/banks/sinopac_v1.py` 的 transaction row regex 與 row filter 可知：目前只有日期 + 商家 + 金額 的行都被收進 `TransactionItem`，沒有判斷「是否為退款行」。永豐帳單的退款行典型特徵：
- 商家字串含「退款」、「退費」、「沖銷」、「取消」字樣
- 或金額為負數（`-1,234`）
- 或行首含 `(-)` / `－` 標記

## What Changes

- **修改 `backend/src/ccas/parser/banks/sinopac_v1.py`**：
  - 新增 `_REFUND_MERCHANT_KEYWORDS = ("退款", "退費", "沖銷", "取消授權", "退貨")` 常數
  - 新增 helper `_is_refund_row(raw_line: str, merchant: str, amount: int) -> bool`：符合任一條件回 `True`
    1. merchant 含任一 refund keyword
    2. amount 為負數
    3. raw_line 行首含 `(-)` 或全形 `－` 前綴
  - 在主 transaction 抽取流程收集 row 之前過濾 refund row
  - **refund row 仍需計入一個獨立統計欄位**（不丟棄），供後續對帳使用：`ParseResult.metadata["sinopac_refund_rows"] = tuple[...]`（若 `ParseResult` schema 不支援 metadata，則暫存 `logger.info` 輸出，不寫入 DB）
- **新增 fixture & 測試**：`backend/tests/integration/parser/fixtures/sinopac/refund_sample.pdf`（脫敏或直接 reference staging path）；新增 `test_sinopac_v1_refund_filter.py` 驗證：
  - 含退款段的 PDF → `transactions` 不含任何 refund keyword
  - 純消費 PDF → `transactions` 行數不回歸

**非範圍**：
- 不改 `ParseResult` schema 加 metadata 欄位（若需要另開 change）。
- 不動 bills.total_amount 計算（仍以 PDF 原始 summary 為準）。
- 不同步處理其他銀行的退款行（各自獨立 change）。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `sinopac-parser`：強化「parse 提取交易明細」需求，加入「退款行 MUST NOT 進入 transactions」的子條件。

## Impact

- **程式**：`backend/src/ccas/parser/banks/sinopac_v1.py`
- **測試**：`backend/tests/integration/parser/test_sinopac_v1_refund_filter.py`、fixtures
- **相容性**：對既有寫入的 SINOPAC row 不 retro-fix；使用者重跑 `pipeline --bank SINOPAC --from parse` 即可清理
- **風險**：keyword 誤命中正常消費（如「取消授權」作為店名）— mitigation：keyword 組合採 AND logic（同時含「授權」+「取消」）
