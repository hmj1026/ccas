## Context

CTBC 信用卡電子帳單的實際發件人為 `ebill@estats.ctbcbank.com`，主旨格式為 `中國信託信用卡電子帳單 XXXXX`（帳單期數）。原本 `banks.yaml` 設定的 filter 從未匹配到任何郵件。已透過 Gmail API `messages.list` 查詢驗證，`from:ebill@estats.ctbcbank.com subject:信用卡電子帳單` 可找到相關郵件。

## Goals / Non-Goals

**Goals:**
- 修正 `config/banks.yaml` 中 CTBC 的 `gmail_filter` 為正確值
- 更新 `config/banks.example.yaml` 保持範本一致

**Non-Goals:**
- 不自動更新 DB（用戶需手動跑 `bank_configs --apply`）
- 不驗證 PDF 附件是否加密（由 decrypt stage 處理）

## Decisions

**D1 — filter 使用 `subject:信用卡電子帳單`（區分銀行對帳單）**

主旨格式為 `中國信託信用卡電子帳單 XXXXX`，使用 `subject:信用卡電子帳單` 可精確篩選信用卡帳單（排除銀行對帳單等其他郵件），且對未來主旨格式微調有一定容忍度。

## Risks / Trade-offs

- [Risk] 未來 CTBC 更換發件地址或主旨 → Mitigation: banks.yaml 設計就是讓用戶可以自行調整 filter
