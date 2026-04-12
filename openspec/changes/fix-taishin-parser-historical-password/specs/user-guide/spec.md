## MODIFIED Requirements

### Requirement: 使用者操作手冊涵蓋完整使用流程

系統 SHALL 提供 `docs/user-guide.md`，涵蓋從環境設定到日常操作的完整流程。PDF 密碼設定章節 MUST 說明當舊期帳單解密失敗時，可透過 `PDF_PASSWORD_<BANK>_LEGACY_N` 設定額外的 legacy 密碼。

#### Scenario: 使用者依文件完成首次設定

- **WHEN** 使用者依照 `docs/user-guide.md` 的步驟操作
- **THEN** 文件 SHALL 引導使用者完成 `.env` 建立、憑證設定、啟動服務

#### Scenario: 使用者執行 pipeline

- **WHEN** 使用者需要手動執行 pipeline
- **THEN** 文件 SHALL 提供 pipeline 執行指令

#### Scenario: 故障排除

- **WHEN** 使用者遇到常見問題
- **THEN** 文件 SHALL 包含故障排除章節

#### Scenario: PDF 密碼章節涵蓋 legacy 密碼

- **WHEN** 使用者設定 `PDF_PASSWORD_<BANK>` 後仍有舊期帳單解密失敗
- **THEN** 文件 SHALL 指引使用者新增 `PDF_PASSWORD_<BANK>_LEGACY_1` 至 `_LEGACY_5` 來提供歷史密碼，並說明解密會按 primary → legacy_1 → ... 順序嘗試
