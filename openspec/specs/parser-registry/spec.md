# parser-registry Specification

## Purpose
TBD - created by archiving change parser-engine. Update Purpose after archive.
## Requirements
### Requirement: 依銀行與版本註冊 parser
系統 SHALL 能依 `bank_code` 與 parser 版本註冊可用的 bank parser，並讓 registry 可列出某家銀行所有已知版本。

#### Scenario: 取得某家銀行的所有 parser 版本
- **WHEN** registry 中已註冊同一銀行的多個 parser 版本
- **THEN** 系統可以依該 `bank_code` 取回對應的 parser 清單

#### Scenario: 未知銀行不回傳 parser
- **WHEN** 某個 `bank_code` 沒有任何已註冊 parser
- **THEN** registry 會回傳空結果，而不是任意猜測其他銀行 parser

### Requirement: 依首選版本與 fallback 順序選擇 parser
系統 SHALL 在執行解析前，先嘗試 `bank_configs.active_parser_version` 指定的 parser；若無法解析，再依版本由新到舊 fallback。

#### Scenario: 先嘗試 active parser version
- **WHEN** 某家銀行設定存在 `active_parser_version`，且 registry 中也存在對應 parser
- **THEN** 該版本會先被排入 parser 嘗試順序的第一位

#### Scenario: 首選版本失敗後回退到其他版本
- **WHEN** 首選 parser 的 `can_parse()` 回傳 false，或其解析流程無法完成
- **THEN** 系統會依版本由新到舊繼續嘗試其他已註冊 parser

