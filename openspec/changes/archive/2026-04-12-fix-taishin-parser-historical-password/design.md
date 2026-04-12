## Context

`Settings.get_pdf_password(bank_code)` 當前只回單一字串，decryptor 只試一次。TAISHIN 舊 PDF 用舊密碼規則，新設定無法解。需要讓 decryptor 能嘗試多組候選密碼。

## Goals / Non-Goals

**Goals:**
- 同一家銀行可設定多組候選密碼，decryptor 依序試解，任一成功即可。
- 既有單密碼設定行為不變（向後相容）。
- 錯誤訊息清楚說明試過幾組、全部失敗。
- 泛用機制適用所有銀行，不特例化 TAISHIN。

**Non-Goals:**
- 不做密碼猜測或 brute-force。
- 不改 `settings.get_pdf_password` 回單一值的行為。
- 不搞安全 vault、加密存放（密碼仍在 `.env`）。

## Decisions

### D1：新 API `get_pdf_passwords` 而非改 `get_pdf_password`

**選擇**：保留 `get_pdf_password(bank_code) -> str | None`（舊），新增 `get_pdf_passwords(bank_code) -> tuple[str, ...]`（新）。Decryptor 改用新 API。

**理由**：
- 單值 API 可能有外部呼叫點（settings page？metrics？），改型別面廣風險高。
- 新 API 名稱清晰表達「多組」。
- 舊 API 內部可改為 `get_pdf_passwords(bank_code)[0] if any else None` 做平行實作。

**Alternatives:**
- (A) 改 `get_pdf_password` 回 `list`：breaking change
- (B) 新 API + deprecate 舊：deprecation cycle 不必要

### D2：Legacy 密碼 env var 命名 `_LEGACY_N` 後綴

**選擇**：`PDF_PASSWORD_TAISHIN`（主要）+ `PDF_PASSWORD_TAISHIN_LEGACY_1`、`_LEGACY_2`... 最多 5 組。

**理由**：
- `_LEGACY_N` 語意清楚，表達「歷史遺留」
- 有限上限（5）避免無限迴圈
- pydantic-settings 可用 `@model_validator` 自動收集

**Alternatives:**
- (A) 單一 env var `PDF_PASSWORDS_TAISHIN` 用分號分隔：parse/escape 麻煩，密碼若含 `;` 會爆
- (B) 用 JSON：`.env` 寫 JSON 醜

### D3：嘗試順序——主密碼優先

**選擇**：tuple 順序為 `(primary, legacy_1, legacy_2, ...)`。

**理由**：新帳單占比高，主密碼先試可縮短一般情境的解密時間。

### D4：全失敗時 error reason 組合

**選擇**：error reason 字串為 `"Invalid password (tried {N} candidates)"`，N 為實際試過的數量（不含 None）。

**理由**：
- 使用者看到 N > 1 能判斷「密碼全錯，不是設定漏」
- 不洩漏密碼本身（redact filter 也不用動）

## Risks / Trade-offs

- **[R1]** 每組密碼試解耗時累加：→ Mitigation：上限 5 組，TAISHIN 實測 ≤ 3 組
- **[R2]** 使用者設錯 legacy 數字順序（`_LEGACY_3` 沒填但 `_LEGACY_5` 有）：→ Mitigation：`get_pdf_passwords` 跳過 None，不強制連號
- **[R3]** 密碼洩漏風險：多組同一家銀行密碼全放 `.env`，若 `.env` 外洩攻擊面擴大。→ Mitigation：既有 `.env` 已屬機敏檔案，本 change 不增加洩漏概率；user-guide 提醒「用完 legacy 可以刪除」

## Migration Plan

1. Settings 改造 + 單元測試
2. Decryptor engine 改用 `get_pdf_passwords`
3. `.env.example` 更新
4. 使用者為 TAISHIN 舊 PDF 填上 `PDF_PASSWORD_TAISHIN_LEGACY_1`
5. 重跑 `pipeline --bank TAISHIN --from decrypt`，抽樣舊期 PDF 解密成功
6. 無 DB migration

## Open Questions

- **OQ1**：是否把 legacy 密碼支援移到 `banks.yaml` per-bank config？決定：**不做**，`.env` 是現行密碼 SSOT，yaml 是公開 config，職責不同。
- **OQ2**：LEGACY 上限 5 合理嗎？決定：足夠；若未來發現需要擴充再 bump。
