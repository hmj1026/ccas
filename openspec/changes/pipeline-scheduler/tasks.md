## 1. Pipeline 協調器

- [ ] 1.1 建立 `run_pipeline()` 函式作為五階段 pipeline 的單一入口，依序呼叫 ingest、decrypt、parse、classify、notify
- [ ] 1.2 實作前一階段成功輸出作為後一階段輸入的資料傳遞機制
- [ ] 1.3 實作各階段摘要聚合，包含 staged/skipped/failed（ingest）、decrypted/failed（decrypt）、parsed/failed（parse）、classified count（classify）、sent/failed（notify）
- [ ] 1.4 實作 pipeline 總耗時追蹤，從入口到所有階段完成為止

## 2. 各階段獨立容錯

- [ ] 2.1 為每個階段實作逐項目的 try/except，確保單筆失敗只影響該項目，不中止整個階段
- [ ] 2.2 實作部分失敗傳遞機制：每個階段只將成功項目傳遞給下一階段，失敗項目記錄於摘要
- [ ] 2.3 確保各階段的錯誤訊息保存到對應的資料庫狀態欄位，支援後續追蹤與重跑
- [ ] 2.4 確保任一階段全部失敗時，後續階段以空列表輸入優雅地空跑並回傳零計數

## 3. 排程設定

- [ ] 3.1 整合 APScheduler `BackgroundScheduler`，在應用程式啟動時初始化並啟動排程器
- [ ] 3.2 註冊週期性 pipeline 排程工作，觸發頻率由 `Settings` 中的設定項目控制（支援 cron 表達式或 interval）
- [ ] 3.3 註冊付款到期前 3 天提醒工作，每日固定時間執行，查詢 `due_date` 等於今日加 3 天的未付帳單
- [ ] 3.4 註冊付款到期前 1 天提醒工作，每日固定時間執行，查詢 `due_date` 等於今日加 1 天的未付帳單
- [ ] 3.5 實作應用程式關閉時的排程器優雅停止（graceful shutdown）

## 4. 手動觸發介面

- [ ] 4.1 實作 CLI 模組入口（`python -m ccas.pipeline`），呼叫 `run_pipeline()` 並將摘要輸出至 stdout
- [ ] 4.2 實作 `POST /api/pipeline/trigger` API 端點，需 Bearer token 驗證，呼叫 `run_pipeline()` 並以 JSON 回傳摘要
- [ ] 4.3 確保 CLI 與 API 端點共用同一個 `run_pipeline()` 實作，行為完全一致
- [ ] 4.4 定義 pipeline 摘要的回應結構（包含各階段統計與總耗時），作為 CLI 輸出與 API 回應的共同格式

## 5. 測試覆蓋

- [ ] 5.1 新增 pipeline 階段順序的單元測試，驗證 ingest → decrypt → parse → classify → notify 的呼叫順序
- [ ] 5.2 新增各階段容錯行為測試，驗證單筆失敗不阻斷整批，且失敗項目不進入下一階段
- [ ] 5.3 新增摘要聚合測試，驗證各階段統計數字正確反映處理結果
- [ ] 5.4 新增排程工作註冊測試，驗證 pipeline 工作與付款提醒工作（3 天、1 天）均被正確註冊
- [ ] 5.5 新增手動觸發測試，分別驗證 CLI 入口與 API 端點能正確呼叫 `run_pipeline()` 並回傳摘要
- [ ] 5.6 新增付款提醒查詢邏輯測試，驗證只有 `due_date` 符合目標日期且未付的帳單會被選出並觸發通知
- [ ] 5.7 新增重複提醒防護測試，驗證同一帳單不會因同一提醒類型被重複通知
