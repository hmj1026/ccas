## 1. Parser 核心介面

- [x] 1.1 建立抽象 parser 介面，定義 `can_parse()` 與 `parse()`
- [x] 1.2 定義 `ParseResult` 資料結構，涵蓋帳單摘要與交易明細
- [x] 1.3 建立 parser 模組目錄與版本化命名慣例

## 2. Registry 與版本選擇

- [x] 2.1 實作依 `bank_code` 與版本註冊 parser 的 registry
- [x] 2.2 實作根據 `active_parser_version` 與版本 fallback 的 parser 選擇邏輯
- [x] 2.3 為未知銀行與無可用 parser 的情境補上錯誤處理

## 3. Parse Orchestration

- [x] 3.1 實作從 staged attachment 觸發 parser orchestration 的流程
- [x] 3.2 在解析成功後建立 `Bill` 與 `Transaction` 紀錄
- [x] 3.3 在解析失敗時更新 staged attachment 狀態為 `parse_failed` 並保存原因
- [x] 3.4 對已完成解析的附件加入去重複保護

## 4. 測試覆蓋

- [x] 4.1 新增 registry 與 parser 選擇順序的單元測試
- [x] 4.2 新增 `ParseResult` 與 parser contract 的單元測試
- [x] 4.3 新增成功解析與失敗標記流程的整合測試
- [x] 4.4 新增同一附件不重複建立帳單資料的測試
