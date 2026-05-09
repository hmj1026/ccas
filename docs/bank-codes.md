# Bank Code 對照表

`bank_code` 是 CCAS 用來識別銀行的正式代碼。  
在 `config/banks.yaml` 裡只能使用 `config/bank-code-registry.yaml` 已定義的值，不建議自行發明。

## 使用方式

1. 先看本表找到正確的 `bank_code`
2. 到 `config/banks.yaml` 填入對應設定
3. 執行 `./scripts/setup.sh`
4. setup 會自動驗證並同步到資料庫

## 對照表

| bank_code | fsc_code | 銀行名稱 | Parser 現況 | 備註 |
|---|---|---|---|---|
| `CTBC` | `822` | 中國信託 | v1 已實作 | `parser/banks/ctbc_v1.py` |
| `CATHAY` | `013` | 國泰世華 | v1 已實作 | `parser/banks/cathay_v1.py` |
| `ESUN` | `808` | 玉山銀行 | v1 已實作 | `parser/banks/esun_v1.py` |
| `TAISHIN` | `812` | 台新銀行 | v1 已實作 | `parser/banks/taishin_v1.py` |
| `FUBON` | `012` | 台北富邦 | v1 已實作 | `parser/banks/fubon_v1.py`（支援 web-fetch 流程） |
| `MEGA` | `017` | 兆豐銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `FIRST` | `007` | 第一銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `SINOPAC` | `807` | 永豐銀行 | v1 已實作 | `parser/banks/sinopac_v1.py` |
| `UBOT` | `803` | 聯邦銀行 | v1 已實作 | `parser/banks/ubot_v1.py` |
| `HSBC` | `081` | 匯豐銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `SCB` | `052` | 渣打銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `LANDBANK` | `005` | 土地銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `TCB` | `006` | 合作金庫 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `HUANAN` | `008` | 華南銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `CHANG_HWA` | `009` | 彰化銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |
| `YUANTA` | `806` | 元大銀行 | 尚未提供正式 parser | 可先配置 Gmail filter 與本地流程 |

## 已合併 / 停止發卡

| 原銀行 / 品牌 | 現況 | 說明 |
|---|---|---|
| 花旗銀行 (`CITI`) | 2023 年消金業務併入星展銀行 | 歷史帳單與卡面仍可能出現花旗名稱，但新支援方向應以合併後發卡行資訊為準 |

## 新增代碼的原則

- 不要直接在 `config/banks.yaml` 自創新代碼
- 先補 `config/bank-code-registry.yaml`
- 再同步更新這份文件與 `fsc_code` 對照欄位
- 若未來有正式 parser，請一併更新 `Parser 現況`
