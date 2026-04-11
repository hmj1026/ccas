# Spec Delta: TAISHIN Parser

## MODIFIED Requirements

### Requirement: TAISHIN 繳款截止日 SHALL 支援無冒號空白分隔

`_RE_DUE_DATE` 與 `_RE_ROC_DUE_DATE` MUST 接受「繳款截止日」後面僅有空白而無冒號的格式。

#### Scenario: 民國年日期無冒號

- **GIVEN** 文字含 `繳款截止日 113/11/27`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2024, 11, 27)`

#### Scenario: 民國年日期有冒號

- **GIVEN** 文字含 `繳款截止日：113/11/27`
- **WHEN** 呼叫 `_extract_due_date`
- **THEN** 回傳 `date(2024, 11, 27)`（向後相容）
