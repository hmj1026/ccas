## ADDED Requirements

### Requirement: Legacy PDF 密碼環境變數校驗

系統 SHALL 允許每家銀行設定 `PDF_PASSWORD_<BANK>_LEGACY_1` 至 `PDF_PASSWORD_<BANK>_LEGACY_5` 共 5 組選用 legacy 密碼。env 驗證腳本 MUST NOT 將 legacy 密碼標記為必要，但若使用者設定了任一 legacy 變數，其值 MUST 非空字串，否則驗證失敗。

#### Scenario: 未設定 legacy 不視為錯誤

- **WHEN** `.env` 只含 `PDF_PASSWORD_TAISHIN` 而無任何 `_LEGACY_N`
- **THEN** `scripts/check-env.sh` SHALL 以 exit code 0 退出

#### Scenario: Legacy 變數設定但值為空字串

- **WHEN** `.env` 含 `PDF_PASSWORD_TAISHIN_LEGACY_1=`（空值）
- **THEN** 驗證腳本 SHALL 報錯並以非零 exit code 退出，訊息指出該變數已設定但為空

#### Scenario: 超過 LEGACY_5 的變數被忽略

- **WHEN** `.env` 含 `PDF_PASSWORD_TAISHIN_LEGACY_6=xxx`
- **THEN** 系統 SHALL 忽略該變數（不讀入 Settings），驗證腳本不報錯
