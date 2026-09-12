# ADR-0001: Agent／Notion 信任邊界與資料庫獨立性

## Status

Accepted（2026-09-10 Paul 拍板；為本專案第一份 ADR）

## Context

CCAS 目前是一套可獨立部署的本機系統：Gmail → 解密 → 解析 → 分類 → REST API／儀表板／預算／Telegram。外部還存在一個獨立運作的 Agent（例如 Grok Bot「信用卡帳單小幫手」），該 Agent 以 Notion 上既有的繳款儀表板、明細、回饋表作為它自己的資料與決策依據。

隨著 Agent 想要更穩定地取得 CCAS 的結構化資料（帳單、交易、到期、預算、pipeline 狀態）以便對帳／驗證，出現了一個必須現在就定案、且事後改變代價很高的問題：**CCAS 與 Notion 誰是誰的「主」？Agent 對使用者做決策時要以哪一邊為準？CCAS 要對外暴露到什麼程度？**

這個問題具備 ADR 的典型特徵：
- **不可逆／難以逆轉**：一旦 Agent 開始依賴某種同步或主從關係運作，之後要改成獨立雙庫會牽動 Agent 端的決策邏輯，而 Agent 端不在本專案的控制範圍內。
- **有明確取捨**：強制雙向同步可以讓兩邊資料一致，但會把 CCAS 綁死在 Agent／Notion 的可用性與 schema 演進上，違反「CCAS 必須可單獨部署、跑完整流程」的硬性前提。
- **跨模組／跨系統**：影響 API 認證模型、MCP／CLI 介面設計、以及未來任何想整合 CCAS 的第三方 Agent。

## Decision

1. **CCAS 與 Notion 是兩個完整、獨立的資料庫，互不為主從。** CCAS 自己管理自己的 pipeline 狀態、付款狀態、解析狀態；Notion 自己管理自己的繳款儀表板、明細、回饋表。本階段**不建立強制雙向同步機制**（不做「改一邊自動改另一邊」）。
2. **決策權永遠在 Notion。** Agent 對使用者做的任何決策——催繳、建議刷哪張卡、判斷「算不算已繳」——一律以 Notion 上的資料為最終依據。CCAS 只提供「事實」供 Agent 驗證／對帳，不作為決策的唯一真相來源。
3. **CCAS 是驗證／對帳來源，不是同步目標。** Agent 需要補漏、比對金額或解析結果時，可以呼叫 CCAS 的介面（見 `agent-mcp-interface`）取數，但取回的資料只用於「跟 Notion 對照」，不能拿去覆寫 Notion，CCAS 也不接受 Agent 拿 Notion 資料回頭覆寫自己的付款／解析狀態（除非透過使用者明確授權的寫入工具，且那些寫入工具只改 CCAS 自己的狀態，永不觸碰 Notion）。
4. **兩邊不一致時，一律標示差異給人看，不擅自覆寫任一方。** 這是 Agent 端的行為約束，但 CCAS 這一側的介面設計必須支援「回傳足以讓 Agent 產生差異報告的結構化資料」（穩定的複合識別鍵，見 `reconciliation-identity`）。
5. **Secrets 永不跨越這個邊界。** PDF 密碼、OAuth refresh token、session secret、完整卡號等，不論透過 MCP、CLI、或未來任何管道，都不得回傳給 Agent、寫進 Notion 或出現在聊天內容中。這是本決策的安全底線，任何未來的介面變更都不得放寬。
6. **連線分期：先本機 stdio，遠端 Streamable HTTP 留待 stdio 穩定後再開。** 在本機 stdio 階段，信任邊界主要靠「同機、行程內連線」本身提供；stdio 遵守 MCP 現行 wire contract，但不套用 HTTP OAuth authorization spec。到遠端階段才需要 Origin 驗證與真正的 token／scope 授權模型，屬於後續 ADR 或本 ADR 的修訂範圍，不在本次決定中展開；新實作不得採用已 deprecated 的 HTTP+SSE transport。

## Consequences

**正面：**
- CCAS 不會因為 Agent／Notion 任一方暫時不可用或改版而停擺，符合「關掉 Agent、關掉 Notion、關掉雲端 AI，本機仍要能用」的硬性前提。
- 不需要處理雙向同步的衝突解決（conflict resolution）邏輯，大幅降低短期複雜度。
- CCAS 對外暴露的介面（MCP/CLI）只需要對「讀取＋驗證」負責，寫入範圍被嚴格限制在 CCAS 自己的狀態，降低誤寫風險。

**需要承擔的代價／後續影響：**
- Notion 與 CCAS 資料可能長期存在差異，需要依賴人工或 Agent 主動比對；規劃中的 Phase 3 change（`add-agent-write-tools-and-events`，目前尚未建立）的「對帳報告工具」可作為這個代價的緩解手段，本身仍不自動改寫任一方。
- 若未來要放寬到雙向同步，需要重新開一份 ADR 明確處理主從與衝突解決策略，不能只靠新增 API 端點默默達成。
- `agent-mcp-interface`／`agent-cli-interface`／`reconciliation-identity` 三份 capability spec（見 `openspec/changes/add-agent-mcp-interface/`）都必須遵守本 ADR 訂下的邊界：預設唯讀、寫入需明確授權、複合鍵只用於對帳而非合併、secrets 永不回傳。

## References

- `openspec/changes/add-agent-mcp-interface/` — MCP／CLI 介面規格，實作本 ADR 的邊界
- `openspec/changes/harden-bill-parsing-pipeline/` — 解析管線強化，與本 ADR 無直接耦合但共享同一份決策文件背景
- `CONTEXT.md` — 「Agent」「對帳」等詞彙定義
- [MCP Architecture](https://modelcontextprotocol.io/specification/2026-07-28/architecture) — host／client／server 與能力宣告
- [MCP Server Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) — tool schema、structured content 與 execution error
- [MCP Stdio Transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio) — newline framing、stdout／stderr 與 EOF 行為
- [MCP Transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) — Streamable HTTP 與 deprecated HTTP+SSE 的分期依據
