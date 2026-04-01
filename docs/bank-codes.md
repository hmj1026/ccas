# Bank Code 對照表

`bank_code` 是 CCAS 用來識別銀行的正式代碼。  
在 `config/banks.yaml` 裡只能使用 `config/bank-code-registry.yaml` 已定義的值，不建議自行發明。

## 使用方式

1. 先看本表找到正確的 `bank_code`
2. 到 `config/banks.yaml` 填入對應設定
3. 執行 `./scripts/setup.sh`
4. setup 會自動驗證並同步到資料庫

## 對照表

| bank_code | 銀行名稱 | Parser 現況 | 備註 |
|---|---|---|---|
| `CTBC` | 中國信託 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `CATHAY` | 國泰世華 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `ESUN` | 玉山銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |

## 新增代碼的原則

- 不要直接在 `config/banks.yaml` 自創新代碼
- 先補 `config/bank-code-registry.yaml`
- 再同步更新這份文件
- 若未來有正式 parser，請一併更新 `Parser 現況`
