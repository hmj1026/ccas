## Context

CCAS 既有實作達到「自動 ingest → decrypt → parse → classify → notify」的完整 pipeline，前端 React dashboard 顯示 Bills / Transactions / Overview / Analytics 四頁，但**所有頁面皆為唯讀**：

- `transactions.tsx` 是表格 + filter，沒有 row 級別的編輯
- `analytics.tsx` 提供月趨勢與類別餅圖，沒有對比、預算、insights
- 後端 `classifier/engine.py` 規則寫死在 code，個人化規則需要改 source code 並重新部署
- `PaymentReminder` 後端 model 存在但前端僅 readonly 顯示在 overview 頁

對比 immich 那種「上傳照片 + 一鍵分類 / 編輯 / 搜尋 / 分享」的完整 self-host 體驗，CCAS 仍停留在「自動 ingest 但不能管理」階段。本 change 補上「管理」面向，讓 CCAS 成為真正可日用的個人帳務工具。

設計約束：
- **既有 pipeline 不能斷**：classify 階段重跑時不能覆寫使用者手動編輯。
- **規則優先序明確可解釋**：使用者期望「我設的規則優先於系統規則」，這是個人化工具的基本契約。
- **預算評估不能阻塞 pipeline**：每日 budget evaluation 走獨立 scheduler job，pipeline classify 階段不需要查 budgets 表。
- **匯出不能 OOM**：使用者可能匯出多年交易（10K+ 筆），CSV / Excel 都必須 streaming。
- **DB 加欄位無破壞性**：既有資料量不大（單人本機自架），但仍以 alembic 加欄位（不 alter type / drop column）為原則。

## Goals / Non-Goals

**Goals:**
- 使用者能在 transaction 詳情頁修改 category、note、tags、merchant_alias，且修改後即使 pipeline 重新分類也不被覆寫。
- 使用者能在 `/settings/rules` 建立個人分類規則（如「`UBER EATS` → 餐飲」），規則優先於系統內建規則。
- 使用者能在 `/settings/budgets` 設月預算（總額 / 類別 / 銀行），超出 80% 推 Telegram + dashboard 顯示警示 banner。
- 使用者能在 `/insights` 看銀行對比、年度對比、商家排行、月對月百分比變化。
- 使用者能匯出 CSV / Excel 給會計師或自己整理。
- 既有 `PaymentReminder` 暴露為前端 CRUD（啟用 / 提前天數 / 通知管道）。

**Non-Goals:**
- 多 user / 共享預算：單 token = 單 user 設計沿用。
- Sub-category / 自訂類別樹：類別仍為平層。
- LLM-based 分類建議：本 change 純 rule-based。
- 跨幣別：CCAS 仍以 NT$ 為主。
- Service worker push notification：仍走 Telegram + UI banner。
- 對既有 transactions 大規模 backfill 編輯欄位（`manual_category_override` 等）：alembic 加欄位後既有 row 預設 false，使用者編輯時才寫入。

## Decisions

### D1：分類優先序為「使用者覆寫 → DB 規則 → engine 內建規則 → 未分類」

選擇：classify 階段針對每筆 transaction：
1. 若 `manual_category_override=true` → 跳過分類、保留既有 `category_id`
2. 否則查詢 `classification_rules`（按 `priority DESC`）找第一個 match → 寫入 category_id、`manual_category_override` 保持 false（系統決策可被新規則覆蓋）
3. 否則走既有 `classifier/engine.py` 內建規則 → 寫入 category_id
4. 否則 → 寫「未分類」category

替代方案考慮：
- **DB 規則覆蓋既有 manual override**：被否決。違反「使用者編輯不被覆寫」原則；使用者個人決策優先於任何規則。
- **engine 內建規則優先 DB 規則**：被否決。使用者期望自己設的規則最高優（除手動編輯外），系統規則應為通用 fallback。
- **完全廢除 engine 內建規則**：被否決。使用者沒設規則時仍需基本分類能力，內建規則是合理 baseline。

理由：「個人決策 > 個人規則 > 系統規則 > 未分類」是個人化工具的標準心智模型，與 Notion / Things / Bear 等個人工具一致。

### D2：Transaction 加 5 欄位、不拆獨立 EAV 表

選擇：直接在 `transactions` 表加 `manual_category_override` (bool, default false)、`note` (text, default '')、`tags` (JSON array, default '[]')、`merchant_alias` (str, default '')、`updated_at` (datetime)。

替代方案考慮：
- **獨立 `transaction_user_data` 表 1:1 join**：被否決。pipeline classify / list query 都要 JOIN，加 N+1 風險；且使用者編輯資料量小，分表沒帶來顯著好處。
- **以 JSON column 統一存所有 user 編輯**：被否決。`manual_category_override` 需要 boolean 索引（classify 階段過濾），JSON 內 boolean 查詢慢。

理由：欄位數可控（5 個）、查詢路徑簡單、ORM 模型一致。

### D3：classification_rules 為純 DB 表，不快取進 backend memory

選擇：classify 階段每次跑 stage 開始時 query `SELECT * FROM classification_rules WHERE enabled = true ORDER BY priority DESC`，stage 內所有 transaction 共用該結果集。Pipeline run 之間不快取（每次 stage 重新 query）。

替代方案考慮：
- **記憶體快取 + invalidate hooks**：被否決。pipeline 為 batch job、單次 run 內已自然複用 query 結果；run 之間使用者可能改規則，每次重 query 比 invalidate 邏輯簡單。
- **純 SQL view 內聯到 classify query**：被否決。匹配邏輯（regex / keyword）在 application 層處理，view 化會把 regex push 到 SQLite（SQLite regex 需擴充模組）。

理由：簡單可預測、單次 pipeline run 規則一致（不會 mid-run 變動）。

### D3.1：規則匹配實作為 application-level，pattern_type 三種

選擇：
- `pattern_type = 'keyword'`：`text.lower().find(pattern.lower()) != -1`，最常見
- `pattern_type = 'exact'`：`text.lower() == pattern.lower()`
- `pattern_type = 'regex'`：`re.search(pattern, text, re.IGNORECASE)`，使用者 UI 端有 regex 提示

匹配對象 SHALL 為 `transaction.description`（既有欄位，從 PDF parse 出的商家描述）。

替代方案考慮：
- **支援匹配 amount 範圍 / date 範圍**：被否決。本 change 範圍收斂為「依商家描述分類」，amount-based 規則列為後續 enhancement。
- **支援 fuzzy matching**：被否決，過度工程；使用者明確的 keyword / regex 已涵蓋多數需求。

理由：三種模式覆蓋 95% use case，UI 端可顯示「測試規則」按鈕讓使用者預覽匹配結果。

### D4：budgets 表三種 scope，scope_ref 統一為 text

選擇：`budgets.scope` enum 三種：
- `monthly_total` — 全月所有交易總和（scope_ref 為 null）
- `monthly_category` — 特定類別月總和（scope_ref 為 `category_id` 字串）
- `monthly_bank` — 特定銀行月總和（scope_ref 為 `bank_code` 字串）

`alert_threshold_percent` 預設 80%，超過 threshold 推 Telegram + 寫 `budget_alerts`；超過 100% 推第二次（不重複推中間數）。

替代方案考慮：
- **scope_ref 拆成 `category_id` 與 `bank_code` 兩欄位**：被否決，三種 scope 互斥、用單一 nullable text 欄位 + scope discriminator 更簡潔。
- **支援週 / 季 / 年預算**：被否決，本 change 範圍收斂為月度，其他列為後續 enhancement。
- **多次 alert（90%、100%、110%）**：被否決，避免訊息轟炸；使用者只需要「快超過了」與「已超過」兩次提醒。

### D4.1：budget_alerts 表存歷史、給 dashboard banner 用

選擇：每次 budget evaluator 觸發 alert 時 INSERT 一筆 `budget_alerts(budget_id, period_year_month, threshold_breached_percent, current_amount, triggered_at)`。Dashboard `/overview` SHALL 查詢「當前月份 + 7 天內」的未確認 alert，顯示 banner；使用者可點「我知道了」UPDATE `acknowledged_at`。

#### Scenario 設計重點：
- 同一預算同月不重複推（80% 與 100% 各一次，共最多 2 alert / budget / month）
- 使用者 acknowledge 後 banner 消失但歷史保留
- Telegram 發送獨立於 banner，不依賴 acknowledge 狀態

### D5：budget evaluator 走 scheduler daily job

選擇：APScheduler 每日 02:00（local time）跑 `evaluate_budgets()`：對每個 enabled budget 計算當月對應 scope 的累計金額、與 threshold 比對、必要時觸發 alert。Job 為冪等：同月同 budget 同 threshold 不重複觸發（用 `budget_alerts` 已存在判斷）。

替代方案考慮：
- **每筆新 transaction 寫入時即時評估**：被否決。pipeline classify 階段已重，加入 budget query 影響 stage 進度寫入頻率；且每日一次足夠（信用卡帳務沒有秒級時敏感性）。
- **手動觸發 + on-demand**：被否決。使用者期待「自動偵測超支」，被動觸發違反承諾。

理由：每日批次最簡單、與 pipeline 解耦、不影響 classify 進度條 UX。

### D6：CSV / Excel streaming export

選擇：
- CSV：用 `csv.writer` + `StreamingResponse`，後端逐筆 yield row、不在 memory 累積完整檔案。
- Excel：用 `openpyxl.Workbook(write_only=True)` + `WriteOnlyCell`，逐筆 append；最後 `wb.save(stream)` 但內部已 streaming。

替代方案考慮：
- **pandas + BytesIO**：被否決。pandas 為重型依賴、且無 streaming 模式（`to_excel` 寫完整 DataFrame）。
- **zip 多 sheet**：被否決，本 change 範圍收斂為單 sheet，未來再擴充。

風險：openpyxl write-only 模式對 styles 支援受限，本 change 不做格式化（只匯出原始資料）；docs 註明「需要格式請匯入會計軟體」。

### D7：/insights 取代 /analytics 並 redirect

選擇：本 change 把 `/analytics` 路由重命名為 `/insights`，舊路由 redirect；NAV 標籤改為「Insights」（中文 UI 顯示為「洞察」）。新頁面為既有 + 新增圖表的合集。

替代方案考慮：
- **`/analytics` 與 `/insights` 並存**：被否決，命名重疊使用者混淆。
- **完全新建 `/insights` 不動 `/analytics`**：被否決，兩頁顯示同類資訊冗餘。

理由：`Insights` 比 `Analytics` 更貼近「洞察 / 提示」的個人化工具語感，符合本 change 整體 UX 升級基調。

### D8：merchant_alias 是 transaction-local，不全域 normalize

選擇：`merchant_alias` 僅作為「該筆交易顯示用名稱」，不嘗試自動 propagate 到其他同 description 的交易（如 `STARBUCKS COFFEE TPE` 改成 `星巴克` 不會自動套用到歷史所有 `STARBUCKS` 交易）。

替代方案考慮：
- **「套用到所有同 description 交易」按鈕**：可行但屬於 batch operation，本 change 範圍收斂；列為 future enhancement。
- **automatic merchant normalization with classification rules**：被否決，與分類規則語意不同（規則改 category，alias 改 displayed merchant）。

理由：避免使用者改 alias 時意外影響歷史資料；明確的「per-row 編輯」語意更安全。

### D9：existing PaymentReminder 模型暴露為 CRUD，不重新設計

選擇：直接暴露既有 `PaymentReminder(bill_id, days_before, channel, enabled)` 模型為 `/settings/reminders` 的 CRUD。`channel` enum 包含 `telegram`、`ui_banner`、`both`。

替代方案考慮：
- **重新設計為「per-bank rules」而非 per-bill**：被否決，既有 model 已能 cover 個別 bill 的彈性；per-bank rules 列為 future enhancement。

理由：既有 model 設計合理，本 change 只是補 UI 層。

## Risks / Trade-offs

- **classification_rules 規則衝突難 debug**：[Risk] 使用者寫多條規則互相覆蓋，不知道為什麼某筆交易被分到 X。Mitigation：UI 提供「測試規則」按鈕，輸入 description 顯示「會匹配到 rule#3 → 餐飲」；transaction 詳情頁顯示「分類來源：使用者覆寫 / rule#3 / 系統規則 / 預設」。
- **regex 規則匹配性能**：[Risk] 使用者寫複雜 regex（catastrophic backtracking）拖累 classify 階段。Mitigation：(a) UI 端顯示「規則複雜度警示」、(b) backend 規則匹配加 timeout（per-rule 100ms），逾時跳過該規則並 log warning、(c) 文件提供 regex best practice 指引。
- **pipeline 重跑覆寫使用者編輯**：[Risk] `manual_category_override` 邏輯出錯導致使用者編輯被覆寫。Mitigation：(a) 寫整合測試覆蓋「編輯 → 重跑 pipeline → 編輯保留」、(b) classify 階段 metric 寫入 `stage_summary` 含「skipped_due_to_manual_override` 數，讓使用者驗證、(c) 重跑前的編輯內容不刪除 `note`、`tags`、`merchant_alias` 欄位。
- **budget alert 噪音**：[Risk] 每月每個 budget 推兩次 Telegram、多預算 + 多月份 = 訊息洪流。Mitigation：(a) 預算 enabled 預設為 false，使用者主動開啟才推、(b) Telegram 訊息聚合：同日多預算超支合併為單則訊息（hourly batch）、(c) UI banner 可批次 acknowledge。
- **匯出大量資料的 timeout**：[Risk] 使用者匯出 5 年資料（50K 筆）時 reverse proxy 或 cloudflare 中間設施 timeout。Mitigation：streaming response + `Transfer-Encoding: chunked`，避免 backend 累積 buffer；docs 註明「巨量匯出建議分年」。
- **既有 transactions 大量資料的 alembic add column 慢**：[Risk] 加欄位在大表上有 lock 風險。Mitigation：本專案 SQLite + 單人資料量小（< 100K 筆），加欄位 + 預設值 < 1 秒；docs 註明「升級時先停 worker 再 migrate 確保 lock 順暢」。
- **insights 查詢 N+1 / scan 全表**：[Risk] 銀行 / 年度對比 query 可能掃全 transactions 表。Mitigation：(a) 既有 `transactions(transaction_date)` index 已存在、補強 `transactions(category_id, transaction_date)` 複合 index、(b) 對比 query LIMIT 24 個月、(c) 使用 SQL aggregate（GROUP BY）而非 Python 端累加。
- **front-end bundle 增大**：[Risk] 新增多個圖表組件、export 對話框、規則編輯器，bundle size 顯著增加。Mitigation：所有新頁面用 lazy route + dynamic import；charts 與 export 對話框 lazy load；測試 bundle size 增量 < 200KB（gzipped）。

## Migration Plan

1. **DB migration**：分兩個 alembic：
   - `<ts>_add_transaction_user_fields.py` — 加 5 欄位、無破壞性、回滾 = drop columns
   - `<ts>_add_user_rules_budgets.py` — 加 3 表（rules / budgets / alerts）、回滾 = drop tables
2. **既有交易資料相容**：alembic 加欄位後既有 row `manual_category_override = false`、`note = ''`、`tags = '[]'`，行為與 change 前一致。
3. **classify 行為變更窗口**：本 change 落地後第一次 pipeline run，新規則表為空、`manual_category_override` 全 false、行為等同 change 前。使用者開始建立規則後，後續 run 才開始走新優先序。
4. **回滾**：alembic downgrade 兩階段 → frontend 對應頁面 lazy route 自動失效（被 redirect 或 404）→ 既有功能完整保留。
5. **Docs 同步**：撰寫 `docs/personal-rules-and-budgets.md` 含完整使用者操作流程、規則 best practice、預算設定範例。

## Open Questions

- 是否在 `/insights` 提供「年度報告」自動生成（PDF）？— 列為後續 enhancement，需要 PDF 生成依賴。本 change 不做。
- 規則跨類別衝突（如同一規則對應多 category）— 本 change 限制 1:1（一規則對應一 category），多 category 列為後續。
- 預算月份起算日（曆月 vs 結帳日）— 本 change 用曆月，符合 self-host 個人工具普遍預期；自訂結帳日列為後續。
- 匯出含 / 不含手動編輯欄位（note, tags）— 本 change 預設含，提供「匯出時包含個人欄位」checkbox。
