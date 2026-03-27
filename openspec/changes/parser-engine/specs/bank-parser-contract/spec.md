## ADDED Requirements

### Requirement: 定義統一的 bank parser 介面
系統 SHALL 為所有 bank parser 定義統一介面，至少包含 `can_parse(pdf)` 與 `parse(pdf)` 兩個方法。

#### Scenario: `can_parse()` 僅負責格式辨識
- **WHEN** parser 收到某份 PDF 輸入
- **THEN** `can_parse()` 只回應該 parser 是否支援該格式，而不負責資料持久化

#### Scenario: `parse()` 回傳結構化結果
- **WHEN** 某個 parser 確認自己可以處理輸入 PDF
- **THEN** `parse()` 會回傳一個結構化 `ParseResult`，供後續 orchestrator 使用

### Requirement: `ParseResult` 必須包含帳單摘要與交易明細
系統 SHALL 定義 `ParseResult`，至少包含帳單月份、應繳總額、到期日與交易明細列表；每筆交易明細需帶有日期、商家、金額與其他可用欄位。

#### Scenario: 解析結果包含帳單主資料
- **WHEN** parser 成功解析一份帳單 PDF
- **THEN** `ParseResult` 會包含足以建立 `Bill` 的主資料欄位

#### Scenario: 解析結果包含多筆交易
- **WHEN** 帳單 PDF 內含多筆消費明細
- **THEN** `ParseResult` 的交易列表會包含所有可辨識交易，供後續建立 `Transaction` 紀錄

### Requirement: `due_date` 必須從 PDF 內容解析取得
系統 SHALL 要求每個 bank parser 從帳單 PDF 中提取繳費截止日（`due_date`），作為 `ParseResult` 的必要欄位。此欄位是 Telegram 到期提醒與 `/upcoming` 功能的資料來源。

#### Scenario: 成功從 PDF 提取到期日
- **WHEN** 帳單 PDF 中包含明確的繳費截止日資訊
- **THEN** parser 會將該日期正規化後填入 `ParseResult.due_date`

#### Scenario: PDF 中無法找到到期日
- **WHEN** 帳單 PDF 中的到期日資訊無法辨識或不存在
- **THEN** parser 會嘗試使用 `bank_configs` 中的 fallback 規則推算到期日；若仍無法判定，則將該附件標記為 `parse_failed` 並記錄缺少到期日的原因
