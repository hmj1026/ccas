# CCAS MCP 安裝與使用

本文件是 CCAS MCP 的安裝 SSOT。CCAS 提供本機 `stdio` MCP server；它只讀取
CCAS 的安全資料投影，不開放寫入工具、不使用網路 transport，也不回傳密碼、OAuth
token、完整卡號或其他 secrets。

## 目前契約

| 項目 | 實作 |
|---|---|
| MCP server | `ccas-mcp`（等同 `python -m ccas.mcp`） |
| Transport | `stdio`；stdout 僅保留 MCP JSON 訊息，診斷訊息走 stderr |
| Tools | `list_bills`、`get_bill`、`query_transactions`、`get_payment_due`、`budget_status`、`pipeline_status` |
| 寫入 | 未提供；`AGENT_WRITE_ENABLED` 不會把目前 server 變成寫入介面 |
| 依賴 | Python 3.12+、uv；`backend/pyproject.toml` 宣告 `mcp>=2.2.0,<3` |

需要了解資料欄位與安全邊界時，先讀 [`current-implementation.md`](CODEMAPS/current-implementation.md)
與 [`0001-agent-notion-trust-boundary.md`](adr/0001-agent-notion-trust-boundary.md)。

## 方式 A：人員手動安裝（本機開發）

1. 取得程式碼並安裝 backend 依賴：

   ```bash
   git clone https://github.com/hmj1026/ccas.git
   cd ccas/backend
   uv sync
   cp ../.env.example ../.env
   export API_TOKEN="$(openssl rand -hex 32)"
   ```

   直接以 `uv` 啟動時，`API_TOKEN` 必須存在於環境或 `.env`；Docker entrypoint
   才會在未設定時自動產生 token。上述 token 僅供本機啟動檢查，請勿貼到對話或提交。

2. 確認 server 可以啟動。這是長駐的 stdio 程序，啟動後不會顯示互動提示；按
   `Ctrl-C` 結束：

   ```bash
   uv run ccas-mcp
   ```

3. 將 MCP client 的 server command 設為下列形式，並把路徑換成絕對路徑：

   ```json
   {
     "mcpServers": {
       "ccas": {
         "command": "uv",
         "args": ["run", "--directory", "/absolute/path/to/ccas/backend", "ccas-mcp"]
       }
     }
   }
   ```

   MCP client 應直接啟動這個 command，不要把 stdout 導向 log 或加入 shell echo。
   若 client 不支援 `--directory`，改用 `cwd=/absolute/path/to/ccas/backend`，command
   為 `uv run ccas-mcp`。

4. 驗證：在 MCP client 中列出 tools，應看到上述六個名稱；再呼叫
   `pipeline_status` 或 `list_bills`。若沒有資料，先依
   [`install-quickstart.md`](install-quickstart.md) 啟動 CCAS 並完成登入。

## 方式 B：委託 AI 安裝

可將下列委託內容貼給具備本機 terminal 與 MCP 設定權限的 AI coding agent：

> 請在 `/absolute/path/to/ccas` 安裝 CCAS MCP。先讀 `docs/mcp-installation.md`、
> `backend/pyproject.toml` 與 `.mcp.json`，確認不要修改 secrets、不要啟用網路
> transport、不要新增寫入工具。執行 `cd backend && uv sync`，以
> `uv run ccas-mcp` 做啟動檢查，然後依我指定的 MCP client 寫入其使用者設定。
> 設定完成後列出實際修改的檔案、啟動 command、六個 tools，以及測試結果；若缺少
> 權限或 client 名稱，停在可恢復的步驟並提出一個明確問題。

AI 執行時必須遵守：

- 先確認目標 client（Claude Desktop、Codex、Gemini CLI 或其他）與設定檔位置，再寫入設定。
- 使用絕對 repository path；不要建立跨 repository symlink，也不要把 `.env`、token、credentials
  或 MCP 設定中的秘密貼到對話或 commit。
- 設定前備份既有 client config；只新增 `mcpServers.ccas`，保留其他 server。
- 安裝後執行一次 `uv run ccas-mcp` 啟動檢查與 client 的 tool discovery；失敗時保留錯誤
  輸出（遮罩秘密）並停止，不要反覆重試或刪除使用者設定。

若 AI 沒有本機寫檔或執行權限，請改用方式 A；AI 只能產生設定片段，不能代替使用者
在 GUI 中授權或輸入秘密。

## 專案內 GitNexus MCP

本 repository 的 [`.mcp.json`](../.mcp.json) 已提供 GitNexus server，供代理進行程式碼
探索與 impact analysis。它與 CCAS 業務 MCP 是兩個不同 server：

- `gitnexus`：程式碼知識圖譜，command 為 `npx -y gitnexus@1.6.3 mcp`。
- `ccas`：業務資料唯讀查詢，command 為上方的 `uv run ... ccas-mcp`。

不要以其中一個取代另一個，也不要把任何一個 server 改成遠端 HTTP endpoint；若要
規劃遠端連線，必須先新增安全與授權設計文件。

## 排錯

| 症狀 | 檢查 |
|---|---|
| `uv: command not found` | 安裝 uv，或改用已安裝的 Python/venv；不要直接使用系統 Python 猜測依賴。 |
| 找不到 `ccas-mcp` | 確認 command 的 `--directory` 指向 `ccas/backend`，並重新執行 `uv sync`。 |
| client 顯示 JSON parse error | 確認 server 使用 stdio，stdout 沒有 shell banner、debug print 或 log。 |
| tools 存在但查不到資料 | 啟動 CCAS backend、確認 data path 與登入狀態，再呼叫 `pipeline_status`。 |
| 需要寫入或同步 Notion | 目前契約不支援；遵守 ADR 的信任邊界，另行提出變更與授權設計。 |
