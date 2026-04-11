# Proposal: Fix UBOT Parser for Real PDF Format

## Why

端到端驗證聯邦銀行（UBOT）pipeline 時，34 份真實 PDF 全數 `parse_failed`：

- 32 份錯誤 `找不到繳費截止日`（parser 預期 `繳費截止日：YYYY/MM/DD` 標籤，實際 PDF 無此字樣）
- 1 份 `can_parse=False`（舊格式 2018 年）
- 1 份「無需繳款」零結帳單（需與 ESUN/SINOPAC 相同處理為 `parse_skipped`）

真實 UBOT 帳單使用「表格網格 + 無標籤欄位」佈局，重要資訊散落於多個相鄰欄位：

```
以下為您01月份之信用卡消費帳單：
6,850 6,850 4,000,000 優惠注意事項     ← 本期應繳 最低應繳 信用額度
115/02/11 已申請自動轉帳                ← 繳款截止日
115/01/27 2.1% 起                       ← 帳單結帳日 + 循環利率
```

且交易明細使用混合格式：本地 `MM/DD MM/DD 商家 TW 金額`、外幣 `MM/DD MM/DD 商家 JP MM/DD JPY 金額 NT金額`、分期調整、負數退款、行動支付 `+` 前綴。

## What Changes

1. **Summary 解析重寫**：
   - 帳單月份：從 `為您XX月份之信用卡消費帳單` + 結帳日 ROC 年推導
   - 應繳總額：match `^NNN NNN NNN 優惠` 首欄
   - 繳款截止日：match `(ROC)/(MM)/(DD) 已申請自動轉帳`
   - 零結帳：`無需繳款` → `ParseError(tag="zero-balance")`（由 `parser/job.py` 路由為 `parse_skipped`）

2. **Transaction 解析重寫**：
   - 新增 `_RE_UBOT_TXN_REAL`：容忍 FX 尾綴、國別碼、負數金額、`+` 行動支付前綴
   - 新增 `_RE_UBOT_CARD_HEADER`：從 `聯邦...卡 －正卡 NNNN` header 追蹤 card_last4
   - 年度補齊：MM/DD 使用 billing_year

3. **保留舊 regex**：既有單元測試使用的 `2026年03月份帳單` / `繳費截止日：...` 格式作為向後相容 fallback。

## Impact

- Affected code: `backend/src/ccas/parser/banks/ubot_v1.py`
- Affected tests: `backend/tests/unit/parser/test_ubot_v1.py`, `backend/tests/unit/parser/conftest.py`
- Affected capability: `ubot-parser` spec
- Data: 34 UBOT 附件可重新解析；1 筆 `11107` 將歸類為 `parse_skipped` (zero-balance)
