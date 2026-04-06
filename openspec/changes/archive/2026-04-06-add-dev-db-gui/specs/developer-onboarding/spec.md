## ADDED Requirements

### Requirement: Development tools documentation

開發者文件 SHALL 包含 GUI 工具的使用說明章節，涵蓋：

1. 可用的 GUI 工具清單與用途
2. 各工具的存取 URL
3. redis-commander 連線確認方式
4. 常見問題排解（port 衝突、資料庫檔案不存在）

#### Scenario: 開發者查閱 GUI 工具說明

- **WHEN** 開發者開啟開發文件
- **THEN** 可找到 SQLite Web GUI 和 redis-commander 的存取方式與啟動指令

#### Scenario: Port 衝突處理

- **WHEN** 預設 port 與其他本地服務衝突
- **THEN** 文件提供修改 port 映射的方法說明
