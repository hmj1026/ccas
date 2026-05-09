## MODIFIED Requirements

### Requirement: Bank code registry

系統 SHALL 維護 `config/bank-code-registry.yaml` 作為有效 `bank_code` 的唯一權威來源，並為每筆記錄提供 `fsc_code`。

Registry 每筆記錄 MUST 包含 `bank_code`、`bank_name`、`fsc_code`，可選 `supported` 和 `notes`。

`fsc_code` MUST 為三位數字字串，保留前導零。

Registry SHALL 至少涵蓋以下銀行代碼：CTBC, CATHAY, ESUN, TAISHIN, FUBON, MEGA, FIRST, SINOPAC, UBOT, HSBC, SCB, LANDBANK, TCB, HUANAN, CHANG_HWA, YUANTA。

#### Scenario: 載入擴充後的 registry

- **WHEN** 使用 `ccas.tools.bank_configs.load_bank_registry()` 載入更新後的 registry
- **THEN** 會回傳包含上述銀行代碼的 lookup dict，且每筆 `BankRegistryEntry` 皆可提供 `fsc_code`

#### Scenario: fsc_code 缺漏或格式錯誤

- **WHEN** registry 某筆記錄缺少 `fsc_code`，或其值不是三位數字字串
- **THEN** `load_bank_registry()` SHALL 拋出 `BankConfigValidationError`

### Requirement: Onboarding documentation

系統 SHALL 提供 `docs/bank-codes.md` 銀行代碼對照表，並與 `config/bank-code-registry.yaml` 維持同步。

文件對照表 MUST 包含 `fsc_code` 欄位。

文件 SHALL 包含「已合併/停止發卡」區段，說明花旗銀行消金業務併入星展銀行等歷史變更。

#### Scenario: 所有 registry 銀行出現在文件中

- **WHEN** 比對 registry 與 `docs/bank-codes.md`
- **THEN** 每筆 registry 中的銀行 SHALL 在文件對照表中有對應列

#### Scenario: 使用者查詢花旗銀行

- **WHEN** 使用者在文件中搜尋「花旗」
- **THEN** SHALL 找到花旗消金業務已於 2023 年併入星展銀行的說明
