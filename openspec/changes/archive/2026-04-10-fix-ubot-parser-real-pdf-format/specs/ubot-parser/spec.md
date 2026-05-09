# Spec Delta: UBOT Parser Real PDF Format

## MODIFIED Requirements

### Requirement: UBOT parser SHALL 解析真實 PDF 佈局

`UbotV1Parser._extract_summary` MUST 辨識真實聯邦銀行帳單的無標籤欄位佈局，提取 billing_month、total_amount、due_date。

#### Scenario: 從「為您XX月份」擷取帳單月份
- **GIVEN** 文字含 `以下為您01月份之信用卡消費帳單：` 與結帳日 `115/01/27 2.1% 起`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2026-01"`

#### Scenario: 從「已申請自動轉帳」擷取繳款截止日
- **GIVEN** 文字含 `115/02/11 已申請自動轉帳`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2026, 2, 11)`

#### Scenario: 從「優惠注意事項」錨點擷取本期應繳總額
- **GIVEN** 文字含 `6,850 6,850 4,000,000 優惠注意事項`
- **WHEN** 呼叫 `_extract_total_amount`
- **THEN** 回傳 `6850`（第一欄即本期應繳總額）

### Requirement: UBOT parser SHALL 處理無需繳款零結帳單

當 PDF 文字含 `無需繳款` 標記時，`_extract_summary` MUST 拋出 `ParseError`，`reason` 含 `zero-balance`，由 `parser/job.py` 路由為 `parse_skipped`。

#### Scenario: 無需繳款標記拋出 zero-balance ParseError
- **GIVEN** 文字含 `無需繳款` 與 `為您07月份之信用卡消費帳單`
- **WHEN** 呼叫 `_extract_summary`
- **THEN** 拋出 `ParseError`，`reason` 包含 `"zero-balance"`

### Requirement: UBOT parser SHALL 解析真實交易行格式

`_extract_transactions` MUST 以行為單位解析真實 PDF 的交易格式，支援本地、外幣、負數、行動支付前綴 `+` 與卡號末四碼追蹤。

#### Scenario: 本地交易含國別碼 TW
- **GIVEN** 文字含 `12/30 12/26 某保險公司 ＸＸＸＸＸＸＸＸＸＸＸ TW 12,152`
- **WHEN** 呼叫 `_extract_transactions`（billing_year=2026）
- **THEN** 產生一筆 `TransactionItem`，`amount=12152`

#### Scenario: 外幣交易含 FX 尾綴
- **GIVEN** 文字含 `01/07 12/31 PRIME MEMBERSHIP MEGURO-KU JP 01/02 JPY 600.00 120`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=120`

#### Scenario: 行動支付 + 前綴
- **GIVEN** 文字含 `+ 02/23 02/17 台灣大創百貨（股）南港ＬａＬａｐｏｒｔ TW 98`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=98`

#### Scenario: 負數退款交易
- **GIVEN** 文字含 `12/31 12/26 專案：想分調整某保險公司 ＸＸＸＸ -12,152`
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 產生一筆 `TransactionItem`，`amount=-12152`

#### Scenario: 卡號末四碼跟隨 header
- **GIVEN** 文字中先出現 `聯邦Ｍ悠遊鈦商卡 －正卡 8000`，之後出現交易行
- **WHEN** 呼叫 `_extract_transactions`
- **THEN** 後續交易的 `card_last4` SHALL 為 `"8000"`
