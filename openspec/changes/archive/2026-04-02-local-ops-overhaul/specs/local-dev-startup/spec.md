## ADDED Requirements

### Requirement: 腳本模式一鍵啟動 backend 與 frontend

系統 SHALL 提供 `scripts/start.sh` 腳本，一條命令同時啟動 backend（uvicorn）和 frontend（vite dev server），並在收到 SIGINT/SIGTERM 時統一清理所有子程序。

#### Scenario: 正常啟動

- **WHEN** 使用者執行 `./scripts/start.sh`
- **THEN** backend SHALL 啟動於 `127.0.0.1:8000`，frontend SHALL 啟動於 `localhost:5173`，兩者同時運行

#### Scenario: 啟動前自動執行 env 驗證

- **WHEN** 使用者執行 `./scripts/start.sh`
- **THEN** 腳本 SHALL 先呼叫 `scripts/check-env.sh`，若驗證失敗則中止啟動並顯示缺漏變數

#### Scenario: Ctrl+C 統一停止所有服務

- **WHEN** 使用者按下 Ctrl+C
- **THEN** 腳本 SHALL 終止 backend 和 frontend 兩個子程序，清理完成後退出

#### Scenario: 啟動後自動 health check

- **WHEN** backend 和 frontend 程序啟動後
- **THEN** 腳本 SHALL 輪詢 backend `/health` 端點和 frontend 根路徑，確認兩者回應正常後輸出就緒訊息

#### Scenario: health check 逾時

- **WHEN** health check 在 30 秒內未收到成功回應
- **THEN** 腳本 SHALL 輸出警告訊息，但不中止已啟動的服務

### Requirement: Docker 模式一鍵啟動

系統 SHALL 確保 `docker-compose up` 為使用者提供完整的一鍵啟動體驗，啟動前自動驗證環境變數。

#### Scenario: docker-compose up 啟動所有服務

- **WHEN** 使用者執行 `docker-compose up`
- **THEN** backend、frontend、redis 服務 SHALL 全部啟動，backend entrypoint SHALL 先執行 env 驗證

#### Scenario: Docker 環境變數缺漏

- **WHEN** `.env` 缺少必要變數且執行 `docker-compose up`
- **THEN** backend 容器 SHALL 在啟動階段輸出缺漏變數清單並以非零 exit code 退出

### Requirement: Startup health check 自動檢查服務狀態

系統 SHALL 在服務啟動後自動檢查 backend 和 frontend 是否正常回應。

#### Scenario: 腳本模式 health check 成功

- **WHEN** `start.sh` 啟動完成且 backend `/health` 回傳 200、frontend 回傳 200
- **THEN** 腳本 SHALL 輸出包含兩個服務狀態的就緒訊息

#### Scenario: Docker 模式 health check

- **WHEN** `docker-compose up` 啟動完成
- **THEN** Docker health check SHALL 確認 backend `/health` 回傳 200
