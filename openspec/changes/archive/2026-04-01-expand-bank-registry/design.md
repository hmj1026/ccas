## Context

CCAS 的銀行代碼主檔 (`config/bank-code-registry.yaml`) 目前僅有 CTBC、CATHAY、ESUN 三家銀行，每筆只有 `bank_code`、`bank_name`、`supported`、`notes` 四個欄位。隨著 parser 開發啟動，需要一套完整的台灣主要銀行代碼作為基礎。

同時，`ccas.tools.bank_configs` 的 `load_bank_registry()` 目前會把 registry YAML 載入為 `BankRegistryEntry`。既然 `fsc_code` 將成為後續 spec 與 parser 模組可依賴的正式欄位，這次 change 需要同步更新 dataclass、loader 與單元測試，而不是只停留在 YAML 文件層。

## Goals / Non-Goals

**Goals:**
- 擴充 bank-code-registry.yaml 至約 16 家台灣主要信用卡發卡行
- 新增 `fsc_code` 欄位（金管會三碼行庫代碼）作為正式系統欄位
- 更新 docs/bank-codes.md 對照表與 registry 同步
- 修正三份平台文件 (CLAUDE.md, AGENTS.md, GEMINI.md) 的 skill 描述不一致

**Non-Goals:**
- 不新增銀行的 parser 實作（由 `ctbc-parser-v1` change 處理）
- 不修改 `config/banks.example.yaml` 或 `config/banks.yaml` 的結構

## Decisions

### D1: bank_code 命名規則

維持現有的大寫英文短碼格式（如 CTBC, CATHAY），不改用金管會三碼數字代碼作為主鍵。

**Why:** bank_code 已深入用於 parser 模組命名 (`ctbc_v1.py`)、環境變數 (`PDF_PASSWORD_CTBC`)、staging 目錄 (`staging/CTBC/`)。改用數字代碼會破壞所有既有慣例。fsc_code 作為輔助欄位供參照即可。

### D2: fsc_code 欄位設計

新增 `fsc_code` 字串欄位（三碼數字，如 "822"），為 registry 每筆記錄的必填欄位。

**Why:** 金管會使用三碼數字作為金融機構代碼，是台灣金融業界的標準。保存為字串而非整數，因為前導零有意義（如 "005" 土地銀行）。

### D3: loader 與型別契約

`BankRegistryEntry` 必須新增 `fsc_code: str` 欄位，`load_bank_registry()` 必須驗證其存在且符合三位數字格式，之後所有 consumer 皆可透過 typed entry 讀取此資料。

**Why:** 若 `fsc_code` 只存在 YAML 原始內容而不進入型別與 loader，後續 spec 雖然依賴它，實作端仍無穩定 API 可讀取，等同規格未真正落地。

### D4: 已合併銀行的處理

花旗銀行消金業務已於 2023 年併入星展銀行 (DBS)，不在 registry 中建立 CITI 條目。在 docs/bank-codes.md 新增「已合併/停止發卡」區段說明。

**Why:** 避免使用者混淆。已合併的銀行帳單格式可能已變更，應以合併後的發卡行為準。

### D5: 平台文件修正範圍

平台文件中的 skill 數量以 repo 內實際目錄為準。若需要提到 ECC / reference / global skills，必須明確標示它們不是本 repo 的 `.claude/skills/`、`.codex/skills/`、`.gemini/skills/` 目錄內容。

**Why:** 最小變更原則。文件結構重組應在獨立的 change 中進行。

## Implementation Notes

- `config/bank-code-registry.yaml` 的每筆 bank record 需加入 `fsc_code`
- `BankRegistryEntry` dataclass 需加入 `fsc_code: str`
- `load_bank_registry()` 需在缺少 `fsc_code`、長度非 3、或含非數字字元時拋出 `BankConfigValidationError`
- 既有只使用 `bank_code`、`bank_name`、`supported`、`notes` 的呼叫端不需要行為修改，但會收到多一個可用欄位

## Risks / Trade-offs

- **[fsc_code 正確性]** fsc_code 對照需以金管會公開資料為準。部分銀行歷經合併可能有多個代碼。Mitigation: 使用最新的銀行代碼，在 notes 欄位記錄歷史變更。
- **[load_bank_registry 相容性]** 新增 `fsc_code` 欄位會改變 registry 的 validation contract。Mitigation: 同步更新 dataclass、loader、單元測試，並保持既有欄位語意不變。
