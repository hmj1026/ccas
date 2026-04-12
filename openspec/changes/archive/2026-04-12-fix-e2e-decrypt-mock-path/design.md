## Context

`ccas.decryptor.job` 模組 import `decrypt_pdf_multi`（來自 `ccas.decryptor.decrypt`），e2e tests 的 `patch("ccas.decryptor.job.decrypt_pdf", ...)` 找不到此 attribute 導致 `AttributeError`。

## Goals / Non-Goals

**Goals:**
- 修正 2 個 e2e test 的 mock target，使其 PASS

**Non-Goals:**
- 不修改 `decrypt_pdf_multi` 的 API signature
- 不重構 e2e test 結構

## Decisions

1. **直接更新 mock path** — `decrypt_pdf` → `decrypt_pdf_multi`，同時需檢查 mock return value 是否與 `decrypt_pdf_multi` 的新簽名相容（multi-password 版本回傳 `DecryptResult` 而非直接 `Path`）。

## Risks / Trade-offs

- [Risk] mock return value 可能也需更新 → 檢查 `DecryptResult` 結構後決定
