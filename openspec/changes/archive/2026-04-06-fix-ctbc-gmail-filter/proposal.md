## Why

`config/banks.yaml` 的 CTBC `gmail_filter` 設定為 `from:service@ctbcbank.com subject:信用卡`，但實際的 CTBC 信用卡電子帳單是從 `ebill@estats.ctbcbank.com` 寄出、主旨為 `中國信託信用卡電子帳單`。錯誤的 filter 導致 ingest stage 永遠找不到任何郵件，整條 pipeline 都會跑出 0。

## What Changes

- `config/banks.yaml` 的 CTBC `gmail_filter` 由 `from:service@ctbcbank.com subject:信用卡` 改為 `from:ebill@estats.ctbcbank.com subject:信用卡電子帳單`
- `config/banks.example.yaml`（若存在）同步更新

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `ctbc-bootstrap`: CTBC 銀行的 Gmail filter 設定值改變

## Impact

- `config/banks.yaml` — `gmail_filter` 值更新
- `config/banks.example.yaml` — 同步更新（作為範本）
- 下一次執行 `python -m ccas.tools.bank_configs --apply` 後，DB 中的 CTBC 設定會更新
