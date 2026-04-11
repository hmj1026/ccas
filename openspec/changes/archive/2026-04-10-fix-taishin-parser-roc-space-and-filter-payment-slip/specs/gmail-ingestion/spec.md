# Spec Delta: Gmail Ingestion Filename Blocklist

## MODIFIED Requirements

### Requirement: 每銀行附件檔名黑名單 SHALL 包含 TAISHIN PaymentSlip

`ATTACHMENT_FILENAME_BLOCKLIST` MUST 包含 `TAISHIN: ("PaymentSlip",)`，使得 `TSB_PaymentSlip_YYYYMM.pdf` 附件在 ingest 階段被略過。

#### Scenario: TAISHIN PaymentSlip 命中黑名單

- **GIVEN** `bank_code="TAISHIN"`、`filename="TSB_PaymentSlip_202411.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 True

#### Scenario: TAISHIN Estatement 不命中

- **GIVEN** `bank_code="TAISHIN"`、`filename="TSB_Creditcard_Estatement_202411.pdf"`
- **WHEN** `should_skip_attachment` 被呼叫
- **THEN** 回傳 False
