## ADDED Requirements

### Requirement: 支援 `/paid {bill_id}` 標記帳單已繳
系統 SHALL 支援 `/paid {bill_id}` 指令，將對應帳單的 `is_paid` 狀態更新為 `true`。

#### Scenario: 成功標記帳單已繳
- **WHEN** 使用者送出 `/paid 123`，且 `bill_id=123` 的帳單存在且尚未繳款
- **THEN** bot 會將該帳單標記為已繳，並回覆成功訊息

#### Scenario: 重複標記已繳帳單
- **WHEN** 使用者送出 `/paid 123`，且 `bill_id=123` 的帳單已經是已繳狀態
- **THEN** bot 會回覆該帳單已是已繳狀態，而不會視為錯誤

### Requirement: 對無效帳單編號回覆明確錯誤
系統 SHALL 在 `/paid {bill_id}` 找不到帳單或參數格式無效時，回覆清楚的錯誤訊息。

#### Scenario: 帳單編號不存在
- **WHEN** 使用者送出 `/paid 999999`，但系統中不存在該帳單
- **THEN** bot 會回覆找不到對應帳單的訊息
