## 1. 文件與規格修正

- [x] 1.1 更新 `proposal.md`、`design.md`、delta spec 與 `tasks.md`：將 bank registry 維持在 `developer-onboarding` capability 內，並明確把 `fsc_code` 定義為正式系統欄位
- [x] 1.2 更新 `CLAUDE.md`、`AGENTS.md`、`GEMINI.md`：使 skill 數量與平台差異描述符合 repo 內實際目錄內容
- [x] 1.3 更新 `docs/bank-codes.md`：加入擴充銀行清單、`fsc_code` 欄位與「已合併/停止發卡」區段

## 2. Registry 與 loader 實作

- [x] 2.1 更新 `config/bank-code-registry.yaml`：為既有三家銀行新增 `fsc_code`，並補齊 TAISHIN、FUBON、MEGA、FIRST、SINOPAC、UBOT、HSBC、SCB、LANDBANK、TCB、HUANAN、CHANG_HWA、YUANTA
- [x] 2.2 更新 `backend/src/ccas/tools/bank_configs.py`：為 `BankRegistryEntry` 新增 `fsc_code`，並在 `load_bank_registry()` 載入與驗證三位數字字串格式
- [x] 2.3 更新 `backend/tests/unit/tools/test_bank_configs.py`：補上 `fsc_code` 的成功與失敗案例

## 3. 驗證

- [x] 3.1 執行 focused pytest，確認 `load_bank_registry()` 與既有 `load_bank_config_specs()` 在新增 `fsc_code` 後仍正常
- [x] 3.2 驗證 `config/bank-code-registry.yaml` 與 `docs/bank-codes.md` 內容同步
