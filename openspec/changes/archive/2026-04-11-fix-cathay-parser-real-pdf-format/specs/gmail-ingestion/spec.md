# Spec Delta: CATHAY Attachment Blocklist

## MODIFIED Requirements

### Requirement: 每銀行附件檔名黑名單 SHALL 過濾非帳單附件

CATHAY 應加入附件檔名黑名單，於 ingest 階段早期略過國泰世華同郵件附帶的「繳款聯」付款憑證，避免污染 staging 與 parser 統計。

#### Scenario: CATHAY 繳款聯附件被黑名單略過
- **GIVEN** bank_code=`"CATHAY"` 且附件檔名為 `國泰世華115年03月信用卡繳款聯.pdf`
- **WHEN** 呼叫 `should_skip_attachment`
- **THEN** 回傳 `True`

#### Scenario: CATHAY 帳單附件不受影響
- **GIVEN** bank_code=`"CATHAY"` 且附件檔名為 `信用卡電子帳單消費明細_11503.pdf`
- **WHEN** 呼叫 `should_skip_attachment`
- **THEN** 回傳 `False`
