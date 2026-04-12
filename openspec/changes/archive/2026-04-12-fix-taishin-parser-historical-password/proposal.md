## Why

E2E walkthrough 問題 #7：TAISHIN 2020 年（舊期）的帳單 PDF 在 decrypt 階段一律拋「Invalid password」，導致舊帳單永遠無法進 parse。查核後確認：

- 目前 `Settings.get_pdf_password("TAISHIN")` 只回傳單一環境變數 `PDF_PASSWORD_TAISHIN`。
- TAISHIN 在過往某個時間點調整過密碼規則（常見案例：身分證後四碼 → 身分證後六碼、或生日格式 `YYMMDD` → `YYYYMMDD`）。使用者只能設定一組密碼，舊期 PDF 用的是舊密碼，新的環境變數無法解開。
- `pdf-decryption` 現行 spec 對「多組候選密碼」沒有任何規範，解密流程試一次就放棄。

使用者唯一 workaround 是每次手動改 `.env`、重跑 pipeline、再改回來 — 不可接受。

## What Changes

- **擴充 `ccas.config.Settings.get_pdf_password`**：
  - 新增每家銀行的「多組密碼 list」支援：除了既有 `PDF_PASSWORD_<BANK>` 單值，另支援 `PDF_PASSWORD_<BANK>_LEGACY_1`、`_LEGACY_2`... 的候選 list。
  - 新增 `Settings.get_pdf_passwords(bank_code: str) -> tuple[str, ...]`：回傳「主要 + 所有 legacy」的順序 tuple，主要排第一（保持向後相容）。
- **修改 `backend/src/ccas/decryptor/engine.py`（或等效模組）**：
  - decrypt 流程改為「依序嘗試 `get_pdf_passwords()` 回傳的候選清單，任一成功即 break」。
  - 若全部失敗，error reason 記錄「tried N passwords, all invalid」，仍標記 `decrypt_failed`。
- **更新 `.env.example`**：示範如何設定 `PDF_PASSWORD_TAISHIN_LEGACY_1` / `_LEGACY_2`，並註明「按歷史順序由新到舊」的填寫慣例。
- **新增測試**：
  - `backend/tests/unit/decryptor/test_multi_password_fallback.py`：mock 兩組 Settings 候選密碼，驗證首組失敗會試第二組、第二組成功則回 `decrypted`
  - `backend/tests/unit/config/test_settings_multi_password.py`：env 只設主 / 同時設主+legacy / 只設 legacy 三種情境
- **更新 `docs/user-guide.md`**：在「PDF 密碼設定」節說明「若舊期帳單解密失敗，可設定 `PDF_PASSWORD_<BANK>_LEGACY_1` 等額外密碼」

**非範圍**：
- 不針對 TAISHIN 自動猜測密碼（仍需使用者提供）。
- 不改其他銀行的 decrypt 邏輯（共用的擴充會一起生效，但測試 fixture 以 TAISHIN 為主）。
- 不動 `settings.get_pdf_password(bank_code)` 的回傳型別（保持單一 string），避免 breaking API；新 helper 為獨立 method。

## Capabilities

### New Capabilities

無。

### Modified Capabilities

- `pdf-decryption`：新增「多組候選密碼依序試解」的需求，主 + legacy 的優先序明確；解密失敗時錯誤訊息 MUST 說明試過的密碼數量。
- `env-validation`：新增多組密碼環境變數的校驗規則（不強制 legacy，但若設定則需非空）。
- `user-guide`：PDF 密碼設定節補充 legacy 欄位說明。

## Impact

- **程式**：`backend/src/ccas/config.py`、`backend/src/ccas/decryptor/engine.py`（或 `banks.py`）
- **測試**：`backend/tests/unit/decryptor/test_multi_password_fallback.py`、`backend/tests/unit/config/test_settings_multi_password.py`
- **設定**：`.env.example`
- **文件**：`docs/user-guide.md`
- **相容性**：既有 `PDF_PASSWORD_<BANK>` 行為不變；`get_pdf_password` 回傳單一值不變；新行為透過 `get_pdf_passwords` 與 engine 內部多嘗試啟用
- **風險**：候選密碼過多時 decrypt 耗時累加（pikepdf 每次試解約 100ms）— 典型場景 ≤ 3 組不成問題
