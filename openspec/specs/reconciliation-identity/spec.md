# reconciliation-identity Specification

## Purpose
TBD - created by archiving change add-agent-mcp-interface. Update Purpose after archive.
## Requirements
### Requirement: Bill 識別鍵為序列化時衍生字串

系統 SHALL 在 MCP／CLI 回應中，為每筆 Bill 提供一個由 canonical-encoded `bank_code`、`billing_month`、以及該帳單底下全部非空 `Transaction.card_last4`（去重、排序後以 `,` 連接）組成的識別字串。若至少有一個末四碼，格式 SHALL 為 `{bank_code}:{billing_month}:{last4s}`；若全部交易皆無末四碼，格式 SHALL 為 `{bank_code}:{billing_month}:due-{due_date.isoformat()}`。此識別鍵 SHALL 不落地為資料庫欄位或唯一約束。

#### Scenario: 單卡帳單

- **WHEN** 某筆 Bill 底下所有 Transaction 的 `card_last4` 都相同（例如 `1234`）
- **THEN** 該 Bill 的識別鍵 SHALL 為 `{bank_code}:{billing_month}:1234`

#### Scenario: 多卡帳單

- **WHEN** 某筆 Bill 底下的 Transaction 橫跨多個 `card_last4`（例如 `1234` 與 `5678`）
- **THEN** 該 Bill 的識別鍵 SHALL 包含排序、去重後以逗號連接的全部末四碼（例如 `1234,5678`）

#### Scenario: 無卡資訊的帳單

- **WHEN** 某筆 Bill 底下所有 Transaction 的 `card_last4` 皆為 `null`（例如手動建立的帳單）
- **THEN** 該 Bill 的識別鍵 SHALL 以 `due_date` 作 fallback，格式為 `{bank_code}:{billing_month}:due-{due_date.isoformat()}`

### Requirement: Transaction 識別鍵為序列化時衍生字串

系統 SHALL 為每筆 Transaction 提供由 canonical-encoded 現況欄位 `bill_id`、`trans_date`、`amount`、`merchant` 組成的識別字串；欄位值中的分隔字元 SHALL 依本文件的 percent-encoding 規則逸出。當同一 Bill 內出現完全相同的四元組時，系統 SHALL 依資料庫 `id` 排序後附加序號後綴以保持唯一。

#### Scenario: 一般交易

- **WHEN** 某筆 Transaction 的四元組在同一 Bill 內唯一
- **THEN** 識別鍵 SHALL 為 `{bill_id}:{trans_date}:{amount}:{merchant}`，不含序號後綴

#### Scenario: 重複四元組交易

- **WHEN** 同一 Bill 內有兩筆 Transaction 的 `trans_date`、`amount`、`merchant` 完全相同
- **THEN** 系統 SHALL 依 `id` 排序後為第二筆起的識別鍵附加 `#2`、`#3` 等序號後綴

### Requirement: CCAS 與 Notion 為獨立資料庫，不自動同步

系統 SHALL 不提供任何自動將 CCAS 資料寫回 Notion、或將 Notion 資料自動寫入 CCAS 的機制。識別鍵僅供 Agent 端比對兩邊資料、產生差異報告使用。

#### Scenario: MCP 回應不觸發任何外部寫入

- **WHEN** Agent 透過任一 MCP 唯讀工具讀取資料
- **THEN** CCAS SHALL 不對 Notion 或任何外部系統發起寫入請求

#### Scenario: 對帳差異交由人工判斷

- **WHEN** Agent 使用識別鍵比對 CCAS 與 Notion 上的同一筆帳單，發現欄位不一致
- **THEN** CCAS 提供的資料本身 SHALL 保持不變，不因比對結果被 Agent 覆寫

