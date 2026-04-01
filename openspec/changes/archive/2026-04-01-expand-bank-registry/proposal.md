## Why

CCAS 的銀行代碼主檔 (`bank-code-registry.yaml`) 目前僅有 3 家銀行 (CTBC, CATHAY, ESUN)，無法覆蓋台灣主要信用卡發卡行。隨著 parser 實作即將啟動，完整的銀行代碼基礎是先決條件。同時，三份平台文件 (CLAUDE.md, AGENTS.md, GEMINI.md) 對 skill 數量和排他性的描述存在不一致，影響多平台開發體驗。

## What Changes

- 擴充 `config/bank-code-registry.yaml` 從 3 家銀行至約 16 家台灣主要信用卡發卡行
- 每筆銀行新增 `fsc_code` 欄位（金管會三碼行庫代碼），並將其納入正式 loader/type，供後續 spec 與 parser 相關模組使用
- 擴充 `docs/bank-codes.md` 對照表，新增「已合併/停止發卡」區段
- 修正 CLAUDE.md、AGENTS.md、GEMINI.md，使其描述與 repo 內實際 skills 目錄內容一致

## Capabilities

### Modified Capabilities

- `developer-onboarding`: 擴充 bank code registry 結構、更新 bank-codes.md 對照表內容、修正平台文件一致性

## Impact

- `config/bank-code-registry.yaml` -- 銀行代碼主檔結構變更（新增 fsc_code 欄位）
- `backend/src/ccas/tools/bank_configs.py` -- `BankRegistryEntry` 與 `load_bank_registry()` 需正式載入並驗證 `fsc_code`
- `backend/tests/unit/tools/test_bank_configs.py` -- 補上 `fsc_code` 的成功與失敗案例
- `docs/bank-codes.md` -- 文件內容大幅擴充
- `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` -- 小幅文字修正
