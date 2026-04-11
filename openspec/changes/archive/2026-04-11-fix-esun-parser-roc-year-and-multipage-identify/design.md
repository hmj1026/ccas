# Design: ESUN Parser Fix

## Context

EsunV1Parser 於規格制定時假設帳單沿用西元年與 NT$ 前綴，實際樣本卻為民國年 + TWD 前綴，且「玉山銀行」四字不出現在首頁。必須以真實 PDF 為 SSOT 調整解析策略。

## Goals / Non-Goals

- Goal: 對既有 37 份真實 ESUN 帳單，pipeline `parse` 階段成功率 100%。
- Goal: 保留向後相容（西元年 + NT$ 樣本若存在仍可解析）。
- Non-Goal: 不重構 classifier / notifier。

## Decisions

### D1: `_identify` 掃描全部頁面

**選項**：(A) 只改 keyword list、(B) 掃全部頁面 join。
**選擇 B**。理由：首頁沒有「玉山銀行」，但 `玉山` + `信用卡帳單` 的組合在全文中極為獨特；若僅改 keyword 易與其他銀行誤判。

### D2: 以 `這是您 XXX年XX月 信用卡帳單` 為 billing_month 主 pattern

真實 PDF 全部以此句開頭，最為穩定。民國年（2-3 位）轉西元 = year + 1911。保留現有 4 位西元 regex 作為 fallback。

### D3: 無標籤 due_date 抓「日期 + 利率百分比」行

ESUN 首頁第 5 行固定為 `YYY/MM/DD X.XX%` 的結構，`\d+\.\d+%` 可視為定錨。此 pattern 需放在現有「繳款截止日」標籤 regex 之後作為 fallback，避免誤抓其他 PDF 的利率行。

### D4: TWD 前綴支援

僅修改 `_RE_TOTAL_AMOUNT` 前綴為 `(?:NT\$?|TWD)?\s*`，不新增額外 pattern。

### D5: MM/DD 交易格式

新增 `_RE_ESUN_TXN_LINE` 放在舊 `_RE_TRANSACTION_LINE` 之前優先嘗試。保留舊 pattern 以相容舊樣本。
