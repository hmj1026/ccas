## MODIFIED Requirements

### Requirement: 依銀行與版本註冊 parser

系統 SHALL 支援透過 import `ccas.parser.banks` 自動載入所有已實作的 bank parser 模組，觸發各模組的 module-level registration，讓對應 parser 完成註冊。

#### Scenario: import banks 套件後 CTBC parser 可用

- **WHEN** 執行 `import ccas.parser.banks`
- **THEN** `registry.resolve("CTBC")` SHALL 成功回傳包含 CTBC v1 parser 的列表

#### Scenario: 新增 bank parser 無需修改 registry 或 job

- **WHEN** 新增一個 bank parser 模組（如 `cathay_v1.py`）並在 `banks/__init__.py` 中 import
- **THEN** `run_parse_job()` SHALL 自動使用新 parser，無需修改 `registry.py` 或 `job.py`
