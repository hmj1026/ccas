## MODIFIED Requirements

### Requirement: 依銀行密碼規則解密加密 PDF

系統 SHALL 從環境變數取得每家銀行的密碼候選清單，包含主密碼 `PDF_PASSWORD_<BANK>` 與選用的 legacy 密碼 `PDF_PASSWORD_<BANK>_LEGACY_1`..`_LEGACY_5`，並**依序嘗試**解密該銀行的 staged PDF。任一候選成功即完成；全部失敗才標記 `decrypt_failed`。候選清單由 `settings.get_pdf_passwords(bank_code) -> tuple[str, ...]` 提供，順序為主密碼優先、legacy 依編號遞增。

#### Scenario: 以主密碼成功解密

- **WHEN** staged PDF 加密，且 `PDF_PASSWORD_<BANK>` 正確
- **THEN** 系統 SHALL 以該密碼解密，staging status 更新為 `decrypted`，legacy 密碼 NOT 被嘗試

#### Scenario: 主密碼失敗 fallback 到 legacy_1

- **GIVEN** `PDF_PASSWORD_TAISHIN` 為新密碼、`PDF_PASSWORD_TAISHIN_LEGACY_1` 為舊密碼
- **WHEN** 某份 2020 年 TAISHIN PDF 主密碼解密失敗
- **THEN** 系統 SHALL 嘗試 legacy_1，若成功則 staging status 更新為 `decrypted`

#### Scenario: 全部候選失敗

- **WHEN** 主密碼與所有 legacy 密碼皆無法解密
- **THEN** 系統 SHALL 將 staging status 更新為 `decrypt_failed`，error reason 字串 MUST 包含 `"Invalid password (tried {N} candidates)"` 其中 N 為實際試過的非空密碼數量

#### Scenario: 銀行無任何密碼設定

- **WHEN** `get_pdf_passwords(bank_code)` 回傳空 tuple 且 PDF 加密
- **THEN** 系統 SHALL 將 staging status 更新為 `decrypt_failed`，error reason 為 `"Password not found in settings"`

#### Scenario: Legacy 編號不連續仍可用

- **GIVEN** 只設定了 `PDF_PASSWORD_TAISHIN` 與 `PDF_PASSWORD_TAISHIN_LEGACY_3`
- **WHEN** `get_pdf_passwords("TAISHIN")` 被呼叫
- **THEN** 回傳 tuple SHALL 為 `(primary, legacy_3)`，跳過未設定的 `_LEGACY_1` / `_LEGACY_2`
