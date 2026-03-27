## 背景 (Context)

CCAS 目前只有 `foundation-setup` 這個基礎建設 change，已規劃 backend/frontend scaffold、資料庫、設定與測試，但尚未定義任何真實帳單資料如何進入系統。產品規格已明確指出帳單來源為 Gmail 信件附件 PDF，因此第一個功能 change 需要把 Gmail 下載流程定義完整，並把輸出切成可供後續 parser change 穩定接手的 staging 邊界。

此 change 同時觸及 Gmail API 整合、檔案落地、資料庫追蹤與 scheduler job 邊界，因此屬於跨模組 change，適合先以 design 鎖定主要技術決策。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 定義 Gmail OAuth 憑證讀取與 API 呼叫邊界
- 依 `bank_configs.gmail_filter` 抓取候選帳單郵件並辨識 PDF 附件
- 將 PDF 附件下載到本地 staging 目錄，使用可預期的檔名與路徑規則
- 保存附件 staging metadata，確保可追蹤、可去重複、可供 parser 接手
- 定義 `run_ingestion_job()` 類型的單次 job 邊界與結果摘要

**非目標：**
- 不實作 PDF 解密與內容解析
- 不建立 bill / transaction 寫入流程
- 不提供前端頁面或 API route

## 決策 (Decisions)

### D1: 搜尋條件完全來自 `bank_configs.gmail_filter`

**選擇**: 每家銀行的 Gmail 搜尋條件以 `bank_configs.gmail_filter` 為唯一來源，ingestion service 不內建銀行專屬規則。

**理由**: 搜尋條件是銀行差異最大的部分，放在資料表中可避免每增加一家銀行就修改程式碼，也符合後續 Settings / Dashboard 維護方向。

**考慮過的替代方案**:
- 在程式內硬編碼各家銀行條件：維護成本高，擴充性差
- 將條件寫在 YAML 檔案：可行，但會和既有 `bank_configs` 職責重疊

### D2: 先做附件 staging，再交由後續 parser 處理

**選擇**: Gmail ingestion 只負責把 PDF 下載到 staging 區並保存 metadata，不直接呼叫 parser。

**理由**: 這可以把外部系統整合問題與 PDF 解析問題分開。當 Gmail 流程或 parser 任一邊失敗時，都能獨立追蹤與重跑。

**考慮過的替代方案**:
- 下載後立即呼叫 parser：端到端較短，但 change 邊界過大，錯誤責任不清楚
- 只下載檔案不入庫：後續難以去重複與追蹤處理狀態

### D3: 去重複鍵值採用 Gmail message 與附件識別資訊

**選擇**: staging record 以 `gmail_message_id` 加附件識別欄位作為唯一識別基礎。

**理由**: 同一封郵件可能有多個附件，單用 message id 不夠；單用檔名又可能碰到銀行每月重複命名。使用 Gmail metadata 最接近來源真相，最適合重跑去重複。

**考慮過的替代方案**:
- 只用檔名去重複：碰到相同檔名容易誤判
- 用檔案 hash 去重複：仍需先下載檔案，成本較高，且無法直接代表 Gmail 來源

### D4: 下載狀態要落地保存，而不是只回傳記憶體結果

**選擇**: 每個候選附件都要有持久化的 staging record，包含 `status` 與 `error_reason`。

**理由**: 未來 parser、人工補救、通知與排程都會依賴附件處理狀態。如果只在執行當下保留結果，之後無法判斷哪些附件失敗、哪些已成功 staged。

**考慮過的替代方案**:
- 只寫 log：不利查詢與補救
- 只在成功時寫資料：失敗案例不可追蹤

### D5: Job 採批次容錯，單筆失敗不中止整批

**選擇**: `run_ingestion_job()` 必須在單封郵件或單個附件失敗時繼續處理其他資料，並回傳成功、略過與失敗統計。

**理由**: Gmail 帳單來源分散，多家銀行資料不應因單筆異常整批失敗。這也較符合後續每日排程的穩定性需求。

**考慮過的替代方案**:
- Fail-fast：實作較簡單，但實務上可用性差
- 對所有錯誤完全吞掉：不利觀測與後續補救

### D6: Pipeline 串接採用同步 orchestrator，支援排程與手動觸發

**選擇**: 定義一個 `run_pipeline()` 入口，依序執行 ingest -> parse -> classify -> notify 四個階段；每個階段獨立容錯，前一階段的新產出自動成為下一階段的輸入。支援 APScheduler 定時觸發與 CLI/API 手動觸發。

**理由**: 四個階段有明確的資料依賴順序（staging -> bills -> classified transactions -> notifications），同步串接最簡單且可追蹤。各階段已有獨立的失敗處理機制，pipeline 只需協調呼叫順序與傳遞階段摘要。

**考慮過的替代方案**:
- 事件驅動 / message queue：對個人工具而言架構過重
- 各階段獨立排程、各自觸發：難以保證執行順序，也不方便看到端到端結果
- 只提供手動觸發：無法自動化每日處理

### D7: Staged PDF 長期保留，由後端提供檔案存取

**選擇**: 已下載的 staged PDF 在解析完成後仍保留在 staging 目錄中，不自動刪除。後端提供檔案存取端點，讓 dashboard 與 Telegram 可以連結到原始 PDF。

**理由**: 使用者可能需要回溯原始帳單 PDF，且儲存量可控（每月每家銀行約一份 PDF）。保留原檔也方便 parser 版本更新後重新解析。

**考慮過的替代方案**:
- 解析後刪除 PDF：節省空間，但失去原始資料回溯能力
- 另存到獨立檔案服務：對個人工具架構過重

## 風險 / 取捨 (Risks / Trade-offs)

**Gmail OAuth token 失效或權限不足** → 啟動或 job 執行時需要回報明確錯誤，並保留重新授權的設定入口
**銀行郵件格式或附件命名不一致** → 此 change 只保證抓取與落地，不處理 parser 判斷，以降低耦合
**附件持久化會增加磁碟使用量** → PDF 每月每銀行約一份，長期保留量可控；未來可加入 retention policy
**新增 staging table 會擴大資料模型** → 以獨立資料表處理，不污染 `bills` / `transactions` 這些尚未解析完成的領域資料
**Pipeline 中間階段失敗可能導致部分完成** → 各階段獨立容錯，pipeline 回傳各階段摘要，方便定位問題
**目前尚未有 main specs** → 此 change 先作為功能規格基礎，後續 archive 時再同步進主規格
