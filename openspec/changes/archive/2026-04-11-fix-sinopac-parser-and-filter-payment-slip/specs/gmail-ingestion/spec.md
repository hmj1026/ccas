## ADDED Requirements

### Requirement: 每銀行附件檔名黑名單過濾

系統 SHALL 支援在 ingestion 階段以 bank_code 為 key 查詢一組附件檔名黑名單（substring match）。當候選 PDF 附件檔名包含黑名單任一 substring 時，系統 SHALL 於 `_process_attachment` 最早階段直接跳過該附件、計入 `summary.skipped_count`，且 MUST NOT 下載、MUST NOT 建立 StagedAttachment 記錄。

黑名單定義於 `backend/src/ccas/ingestor/filters.py`。SINOPAC 的黑名單 SHALL 至少包含 `"繳款聯"`。

#### Scenario: SINOPAC 的繳款聯附件被 skip
- **WHEN** ingestion 處理 SINOPAC 某封郵件，且該郵件附件檔名為 `永豐銀行信用卡繳款聯.pdf`
- **THEN** 系統 SHALL 不下載該附件、不建立 StagedAttachment 記錄，並將其計入 `summary.skipped_count`

#### Scenario: 同封郵件中的帳單附件仍會 stage
- **WHEN** ingestion 處理 SINOPAC 某封郵件，該郵件同時包含 `永豐銀行信用卡帳單.pdf`（part_id=1）與 `永豐銀行信用卡繳款聯.pdf`（part_id=2）
- **THEN** 系統 SHALL 僅 stage `永豐銀行信用卡帳單.pdf`，跳過繳款聯

#### Scenario: 無黑名單銀行不受影響
- **WHEN** ingestion 處理其他銀行（例如 CTBC）的附件
- **THEN** 系統 SHALL 維持原有行為，不套用黑名單過濾
