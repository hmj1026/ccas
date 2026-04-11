## MODIFIED Requirements

### Requirement: parse 提取帳單摘要

`SinopacV1Parser.parse()` SHALL 從永豐帳單 PDF 提取帳單月份（billing_month）、應繳總額（total_amount）、繳費截止日（due_date）。

due_date regex MUST 接受「冒號可有可無」的格式，例如 `您的繳款截止日2026/03/27`（實際帳單無冒號）與 `繳款截止日：2026/03/27` 皆須命中。

total_amount MUST 從帳單摘要表的「臺幣」列抽取「本期應繳總金額」欄（於 `臺幣 上期 已繳 新增 循環 違約 本期應繳 最低` 7 欄表列中為第 6 欄，index = 5）。MUST NOT 依賴 `應繳總金額` 關鍵字直接配對數字（實際 PDF 該關鍵字與數字不在同一行）。

#### Scenario: 成功提取含金額的帳單摘要
- **WHEN** PDF 首頁包含 `您的繳款截止日2026/03/27` 與 `臺幣 7,147 7,147 12,579 0 0 12,579 1,311`
- **THEN** `ParseResult` SHALL 得到 `billing_month="2026-03"`、`total_amount=12579`、`due_date=date(2026,3,27)`

#### Scenario: 支援冒號格式（舊格式或其他版型）
- **WHEN** PDF 包含 `繳款截止日：2026/04/01`
- **THEN** 解析結果 SHALL 正確擷取 `due_date=date(2026,4,1)`

#### Scenario: 摘要欄位缺失時拋出 ParseError
- **WHEN** PDF 中找不到必要的摘要欄位（月份、金額或到期日）且非零額帳單
- **THEN** SHALL 拋出 `ParseError`，包含缺失欄位的說明

### Requirement: parse 提取交易明細

`SinopacV1Parser.parse()` SHALL 從永豐帳單 PDF 提取所有消費交易明細。交易來源於帳單明細頁的表格，表頭包含 `入帳起息日`、`卡號末四碼`、`帳單說明`、`臺幣金額` 等欄位（系統 SHALL 以 `入帳` 與 `臺幣金額` 作為 header 關鍵字判斷交易表）。

Row 格式 SHALL 接受 `MM/DD MM/DD 4digit merchant amount` 的形態（消費日、入帳起息日為 MM/DD，年份以 billing_year 補齊；卡號末四碼為 4 位數字；`merchant` 可含中英文與空白；`amount` 為整數或帶千分號的正負整數）。

#### Scenario: 成功提取多筆 MM/DD 格式交易
- **WHEN** 帳單明細頁包含形如 `02/18 02/24 4300 悠遊卡自動加值─台北捷 500` 的多筆交易列
- **THEN** `ParseResult.transactions` SHALL 包含對應的 `TransactionItem`，`trans_date` 為 `date(billing_year, 2, 18)`、`posting_date` 為 `date(billing_year, 2, 24)`、`card_last4` 為 `"4300"`、`merchant` 為 `"悠遊卡自動加值─台北捷"`、`amount` 為 500

#### Scenario: 支援負數退款交易
- **WHEN** 交易列金額為負值，例如 `03/05 03/05 永豐自扣已入帳，謝謝！ -7,147`
- **THEN** 該交易的 `amount` SHALL 為 `-7147`（自扣/退款不應中斷 parser）

#### Scenario: 可選欄位正確處理
- **WHEN** 交易行包含入帳日與卡號末四碼
- **THEN** `TransactionItem` SHALL 填入 `posting_date` 與 `card_last4`

#### Scenario: 無法解析的交易行被跳過
- **WHEN** 某些交易行格式異常無法解析
- **THEN** parser SHALL 記錄 warning 並跳過該行，不中斷整體解析

## ADDED Requirements

### Requirement: 零額歷史帳單以 ParseError skip 標記

永豐早期帳單若整月無消費，首頁會出現 `您的繳款截止日臺幣金額無需繳款` 字樣且本期應繳總金額為 0，無明確 due_date。系統 SHALL 在此情境下拋出 `ParseError` 並以 reason 標示 `"zero-balance historical bill"`，由上層 parse job 視為 skipped（而非 failed）記錄於統計。

#### Scenario: 偵測到零額帳單拋出可識別 ParseError
- **WHEN** PDF 首頁包含 `無需繳款` 字樣
- **THEN** `SinopacV1Parser.parse()` SHALL 拋出 `ParseError`，訊息包含 `"zero-balance"` 關鍵字以便 job 層識別並標記為 skipped

#### Scenario: 非零額帳單不受影響
- **WHEN** PDF 首頁不含 `無需繳款` 字樣
- **THEN** 系統 SHALL 依一般流程解析
