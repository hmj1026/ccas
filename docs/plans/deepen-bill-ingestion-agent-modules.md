# 帳單、匯入與 Agent module 深化計畫

## 範圍與順序

依序實作三項，保留現有對外行為；不更動 ADR-0001 的唯讀 Agent 與敏感資料限制，亦不實作仍為 Proposed 的 ADR-0002。

1. **信用卡帳單讀取**：以完整、具型別的原生帳單資料取代依 id 拼接的 metadata；網頁列表與付款狀態更新共用映射，Agent 保留 Money、穩定識別鍵與安全檢查。內部 PDF 可用性不得進入 Agent payload。
2. **帳單附件持久化**：集中兩種帳單來源共用的逐筆寫入、commit、rollback 與提交後舊檔清理；來源 adapter 保留下載及失效連結差異。匯入迴圈不再負責持久化順序，進度回報失敗仍不能回滾已提交資料。
3. **Agent 查詢結果**：集中 CLI 與 MCP tool 的人工介入判定；各 adapter 保留退出碼、通訊錯誤與呈現。MCP resource 保持原始狀態快照，不套用工具錯誤政策。

## 設計判準

- depth 來自 caller 不必知道內部協定，不能只增加轉呼叫 module。
- interface 是測試表面；SQLite、暫存檔案及既有 CLI/MCP 契約測試驗證可觀察結果。
- 已有真實 adapter 才保留 seam，不建立通用查詢框架或逐函式的 port。
- locality：帳單欄位、持久化順序、人工介入政策各集中一處。
- leverage：每項既有兩種以上使用情境，不新增假想需求。
- 檔案與 SQLite 並非共同原子交易；失敗可留下無參照檔案，但提交失敗不可清除仍被引用的舊檔。

## 驗證與交付

- 每項先加入有意義的失敗測試，再實作與通過目標測試。
- 帳單：原生金額、PDF 有無、列表與更新一致、分頁及 Agent 安全投影。
- 匯入：兩來源、去重、force／failed 重試、commit 失敗、cleanup 失敗及進度防護。
- Agent：六種成功查詢、一般失敗／重試耗盡、CLI/MCP 錯誤一致與 resource 快照。
- 執行 lint、型別檢查、後端 unit coverage 與 integration／E2E；審查 HIGH／CRITICAL 影響區域。
- Gitflow：從 develop 建立 feat 分支，依三項順序提交，PR 合回 develop；全部 CI 通過且審查問題解決後自動合併。

GitNexus 初步影響：帳單共用查詢 HIGH（網頁、CLI、MCP）；CLI 共用入口 CRITICAL（六個指令）；匯入入口 LOW（pipeline dispatcher，間接影響 CLI／worker）。這些分類要求額外審查與契約驗證，不代表已發現錯誤。
