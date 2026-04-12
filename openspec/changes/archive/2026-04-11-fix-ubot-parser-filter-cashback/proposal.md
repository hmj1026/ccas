## Why

E2E walkthrough 問題 #5：UBOT（聯邦銀行）parser 將帳單末段的「現金回饋入帳」、「紅利折抵」、「退款」行與正常消費行一併寫入 `transactions`，影響：

- 月度消費金額統計虛低或抵消（回饋金額被當成消費反算）
- classifier 把「現金回饋入帳 -500」當成未分類新消費
- 前端 `/transactions?bank_code=UBOT` 出現使用者無法辨識的「回饋」行

UBOT 回饋行典型特徵：
- 商家字串含「回饋」、「紅利折抵」、「退款」、「現金回饋」、「抵扣」
- 金額常為負數（帳單上以 `-` 表示入帳）
- 或行首 `(-)` 標記

本 change 結構與 Change #5（SINOPAC refund filter）同構，但 keyword set 不同。**故意不合併** — 各銀行 parser 應獨立維護自己的 filter 規則，避免跨銀行 regression。

## What Changes

- **修改 `backend/src/ccas/parser/banks/ubot_v1.py`**：
  - 新增 `_CASHBACK_KEYWORDS = ("現金回饋", "回饋入帳", "紅利折抵", "抵扣", "退款", "退貨", "沖銷")` 常數
  - 新增 `_is_cashback_row(raw_line: str, merchant: str, amount: int) -> bool`：
    - 條件 A：merchant 前綴或整字命中 keyword
    - 條件 B：`amount < 0`
    - 條件 C：行首 `(-)` / `－`
  - 主 transaction 抽取流程 filter 掉 cashback row
- **新增測試**：
  - `backend/tests/integration/parser/test_ubot_v1_cashback_filter.py` — 針對含回饋段的 fixture PDF assert
  - `backend/tests/unit/parser/test_ubot_is_cashback_row.py` — 正反例單元測試

**非範圍**：
- 不動 `billing_month` / `total_amount` / `due_date` 擷取。
- 不保留 cashback row 到 DB（與 Change #5 同策略）。
- 不改 `ParseResult` schema。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `ubot-parser`：強化「parse 提取交易明細」需求，加入「回饋/折抵/退款行 MUST NOT 進入 transactions」的子條件。

## Impact

- **程式**：`backend/src/ccas/parser/banks/ubot_v1.py`
- **測試**：`backend/tests/integration/parser/test_ubot_v1_cashback_filter.py`、`backend/tests/unit/parser/test_ubot_is_cashback_row.py`、fixture PDF
- **相容性**：已寫入的錯誤 row 不 retro-fix，使用者重跑 pipeline 即可清
- **風險**：商家名稱真含「回饋」/「折抵」字樣會誤刪 — mitigation：前綴 anchoring + TDD 正反例
