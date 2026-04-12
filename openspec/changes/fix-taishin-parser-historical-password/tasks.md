## 1. TDD 前置（RED）

- [ ] 1.1 新增 `backend/tests/unit/config/test_settings_multi_password.py`：
  - 只設主密碼 → `get_pdf_passwords()` 回 `(primary,)`
  - 主 + legacy_1 → `(primary, legacy_1)`
  - 只設 legacy_1（無主） → `(legacy_1,)`
  - 跳號：主 + legacy_3 → `(primary, legacy_3)`
  - 超過 5 組 → `_LEGACY_6` 被忽略
- [ ] 1.2 新增 `backend/tests/unit/decryptor/test_multi_password_fallback.py`：
  - 主密碼成功：legacy 不被嘗試
  - 主失敗、legacy_1 成功：回 `decrypted`
  - 全失敗：error reason 含 `"tried 3 candidates"`
  - 空 tuple：error reason 為 `"Password not found in settings"`
- [ ] 1.3 `cd backend && uv run pytest tests/unit/config/test_settings_multi_password.py tests/unit/decryptor/test_multi_password_fallback.py -x` 確認 RED

## 2. Settings 改造

- [ ] 2.1 在 `backend/src/ccas/config.py` 新增 `get_pdf_passwords(self, bank_code: str) -> tuple[str, ...]`
- [ ] 2.2 實作：讀取 `PDF_PASSWORD_<BANK>` 當 primary，掃 `_LEGACY_1`..`_LEGACY_5` 依編號排序過濾非空，組裝 tuple（primary 優先）
- [ ] 2.3 保留 `get_pdf_password`（回第一個或 None）向後相容
- [ ] 2.4 pydantic-settings 需用 `@model_validator(mode="after")` 或直接讀 env，視既有風格

## 3. Decryptor 改造

- [ ] 3.1 在 `backend/src/ccas/decryptor/engine.py`（或相當模組）找到 decrypt entry，將 `get_pdf_password` 呼叫點改為 `get_pdf_passwords`
- [ ] 3.2 迭代 tuple 嘗試解密，任一成功即 break
- [ ] 3.3 全失敗時 error reason 組合 `"Invalid password (tried {len(tuple)} candidates)"`
- [ ] 3.4 空 tuple error reason 維持 `"Password not found in settings"`
- [ ] 3.5 重跑 1.3 測試 → GREEN

## 4. `.env.example` 與文件

- [ ] 4.1 `.env.example` 新增 TAISHIN legacy 範例與註解
  ```
  # PDF_PASSWORD_TAISHIN_LEGACY_1=  # 舊密碼 1（若 2020 年前帳單解密失敗時填入）
  # PDF_PASSWORD_TAISHIN_LEGACY_2=
  ```
- [ ] 4.2 `docs/user-guide.md` 的 PDF 密碼章節新增一段說明 legacy 機制
- [ ] 4.3 troubleshooting 新增「舊期帳單解密失敗」條目

## 5. check-env.sh 更新（可選）

- [ ] 5.1 若 `scripts/check-env.sh` 已處理空值檢查，確認 legacy 空字串會被偵測
- [ ] 5.2 若沒有則補 regex：`grep -E '^PDF_PASSWORD_[A-Z]+_LEGACY_[1-5]=$'` 偵測設定但空值

## 6. 手動驗收

- [ ] 6.1 使用者在 `.env` 填 `PDF_PASSWORD_TAISHIN` 與 `PDF_PASSWORD_TAISHIN_LEGACY_1`（舊密碼）
- [ ] 6.2 `docker compose restart backend`
- [ ] 6.3 `docker exec ccas-backend-1 uv run python -m ccas.pipeline --bank TAISHIN --from decrypt --to decrypt`
- [ ] 6.4 抽樣 2020 年 TAISHIN PDF 確認 decrypt status = `decrypted`

## 7. 回歸驗證

- [ ] 7.1 `cd backend && uv run pytest tests/unit/decryptor/ tests/unit/config/ -x`
- [ ] 7.2 `cd backend && uv run pytest -k taishin -x`
- [ ] 7.3 在 `docs/e2e-user-guide-walkthrough.md` 問題 #7 狀態改 `archived`，`對應 change slug` 填 `fix-taishin-parser-historical-password`
- [ ] 7.4 `openspec verify fix-taishin-parser-historical-password` 通過
