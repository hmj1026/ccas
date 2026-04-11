# Spec Delta: CATHAY Parser Real PDF Format

## MODIFIED Requirements

### Requirement: can_parse 透過全部頁面辨識國泰世華帳單

`CathayV1Parser.can_parse()` SHALL 掃描 PDF 全部頁面文字辨識「國泰世華」與「信用卡」關鍵字，不再僅限 page 0，以因應真實 PDF page 0 被 CID 字型遮蔽的情境。

#### Scenario: page 0 關鍵字遮蔽但後續頁面可辨識
- **GIVEN** PDF page 0 的 `extract_text()` 不含「國泰世華」（因收件人姓名 CID 字型）
- **AND** page 1 含「國泰世華」與「信用卡」
- **WHEN** 呼叫 `can_parse`
- **THEN** 回傳 `True`

#### Scenario: 全部頁面皆無關鍵字
- **WHEN** 所有頁面文字皆不含「國泰世華」
- **THEN** `can_parse` 回傳 `False`

### Requirement: CATHAY parser SHALL 解析多版帳單 summary 佈局

`CathayV1Parser._extract_summary` MUST 支援以下 billing_month / due_date 錨點組合：

#### Scenario: 舊版「以下為您YYY年MM月份」月份錨點
- **GIVEN** 文字含 `以下為您108年5月份的信用卡電子帳單`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2019-05"`

#### Scenario: 新版「信用卡帳單 YYY年MM月」月份錨點
- **GIVEN** 文字含 `信用卡帳單 115年3月`
- **WHEN** 呼叫 `_extract_billing_month`
- **THEN** 回傳 `"2026-03"`

#### Scenario: 「繳款截止日(遇假日順延)」無冒號錨點
- **GIVEN** 文字含 `繳款截止日(遇假日順延) 108/06/01`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2019, 6, 1)`

#### Scenario: 「帳款將於」扣款日錨點
- **GIVEN** 文字含 `您的新臺幣帳款將於 115/04/01 (遇假日順延)`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2026, 4, 1)`
