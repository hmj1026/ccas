## 背景 (Context)

在 `foundation-setup` 與 `gmail-ingestor` 之後，系統已具備基礎架構與 Gmail 附件 staging 能力，但仍缺少從 PDF 轉成 `Bill` 與 `Transaction` 的核心解析邏輯。銀行帳單格式會隨時間更動，因此 parser 不能是單一檔案對單一銀行的硬編碼實作，而需要支援版本化與回退策略。

本 change 的範圍集中在 parser engine 本身，不處理分類、Telegram、API 或 dashboard。

## 目標 / 非目標 (Goals / Non-Goals)

**目標：**
- 定義所有 bank parser 共用的抽象介面與輸出資料契約
- 依銀行代碼與版本管理 parser，支援優先版本與 fallback
- 將 staged PDF 成功解析後寫入 `bills` 與 `transactions`
- 對解析失敗附件標記 `parse_failed` 並保留錯誤原因
- 讓後續流程可以從狀態辨識待人工審查的附件

**非目標：**
- 不處理 Gmail 搜尋與附件下載
- 不處理商家分類
- 不發送 Telegram 通知
- 不建立人工審查 UI，只定義資料狀態

## 決策 (Decisions)

### D1: 所有 parser 都實作 `can_parse()` 與 `parse()`

**選擇**: 每個 bank parser 都必須提供 `can_parse(pdf)` 與 `parse(pdf)` 兩個方法。

**理由**: `can_parse()` 可用於快速判斷是否符合某個版本格式，`parse()` 則負責真正產出結構化資料。這可以把格式辨識與解析執行分離，提升 fallback 策略的可控性。

**考慮過的替代方案**:
- 只提供 `parse()`：失敗時難以區分「不支援此格式」與「解析程式異常」
- 單一大型 parser：銀行格式差異過大，不利維護

### D2: 先嘗試 `active_parser_version`，再依版本由新到舊 fallback

**選擇**: 若 `bank_configs.active_parser_version` 對應的 parser 存在，先嘗試該版本；若無法解析，再以版本號由新到舊依序 fallback。

**理由**: 這保留了設定層對當前首選 parser 的控制權，同時不失去 fallback 能力，能更安全地應對格式切換期。

**考慮過的替代方案**:
- 永遠只試最新版本：不利手動固定穩定版本
- 永遠只試 `active_parser_version`：缺少自動回退能力

### D3: `ParseResult` 只承載正規化的帳單與交易資料，`due_date` 必須從 PDF 解析取得

**選擇**: `ParseResult` 負責傳遞 `billing_month`、`total_amount`、`due_date` 與交易明細列表，不直接耦合 ORM model。`due_date`（繳費截止日）是每份帳單 PDF 內的必要欄位，各家銀行 parser 必須從 PDF 中提取此資訊。

**理由**: 解析邏輯與資料持久化分離後，單元測試較容易，也更方便後續調整儲存層。`due_date` 來自 PDF 而非固定設定，因為同一家銀行的到期日可能因帳單月份而異，且 Telegram 提醒與 `/upcoming` 功能都依賴準確的到期日。

**考慮過的替代方案**:
- 直接回傳 ORM objects：解析層與 storage 耦合過高
- 回傳未正規化原始表格：後續流程仍需重複整理欄位
- 將 due_date 設為固定值（例如每月 X 日）：同一銀行不同月份可能不同，且無法適應銀行調整

### D4: 解析失敗以 staged attachment 狀態表示，不新增獨立 queue table

**選擇**: 當所有 parser 版本都無法處理某個附件時，將其 staging status 更新為 `parse_failed`，並記錄錯誤原因。

**理由**: 人工審查佇列本質上是「哪些 staged attachment 尚未被成功解析」，可以直接由狀態推導，不需要額外資料表。

**考慮過的替代方案**:
- 新增專屬 review queue table：資料重複，維護成本較高
- 僅寫 log：無法穩定查詢待處理項目

### D5: 解析成功後由 orchestrator 寫入 `bills` 與 `transactions`

**選擇**: parser engine 的 orchestrator 在解析成功後一次性建立對應的 `Bill` 與多筆 `Transaction`。

**理由**: 帳單與交易明細屬於同一次解析的原子結果，應由同一個協調流程負責保存，後續 classifier 只需補分類欄位。

**考慮過的替代方案**:
- 只回傳 `ParseResult` 由其他服務寫入：責任邊界不清楚
- 由各 parser 自己寫資料庫：測試困難且耦合高

## 風險 / 取捨 (Risks / Trade-offs)

**銀行格式變動頻繁** → 透過版本化 parser 與 fallback 降低一次性失效風險
**`can_parse()` 可能誤判** → 要求每個 parser 同時有辨識與實際解析測試
**同一附件重複解析會造成重複資料** → 由 staging 狀態與 `bills` 唯一約束共同防止重複寫入
**人工審查暫時只有狀態沒有 UI** → 先保留可查詢狀態，後續再由 API / dashboard 補介面
**PDF 中找不到 due_date** → parser 應將其標記為解析警告，使用 `bank_configs` 中的 fallback 規則（如固定日期）作為備援；若完全無法判定，標記為 `parse_failed`
