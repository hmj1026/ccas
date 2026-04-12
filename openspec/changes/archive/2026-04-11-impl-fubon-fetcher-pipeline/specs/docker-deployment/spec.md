## ADDED Requirements

### Requirement: Docker image SHALL 預載 EasyOCR 模型權重

Backend Docker image build 階段 SHALL 預下載 EasyOCR 英文模型權重（`craft_mlt_25k.pth` + `english_g2.pth`），避免容器 runtime 首次呼叫 FUBON fetcher 時才觸發下載（會拖長啟動時間且依賴 runtime 對外網路）。

#### Scenario: image 內包含 EasyOCR 權重檔

- **WHEN** backend image build 完成後檢查 `/root/.EasyOCR/model/` 或對應使用者家目錄
- **THEN** 目錄 SHALL 存在 `craft_mlt_25k.pth` 與 `english_g2.pth` 兩個檔案

#### Scenario: 容器啟動後第一次呼叫不觸發下載

- **WHEN** 容器 fresh 啟動後首次執行 FUBON fetcher，且 runtime 無對外網路存取
- **THEN** EasyOCR `Reader(['en'])` SHALL 成功初始化，不拋出下載相關錯誤

### Requirement: Docker Compose SHALL 將 FUBON 專屬 env 視為可選

`docker-compose.yml` 與 `x-shared-env` anchor SHALL 將 `FUBON_ID_NUMBER`、`FUBON_BIRTHDAY`、`FUBON_CAPTCHA_MAX_RETRIES`、`FUBON_CAPTCHA_FALLBACK_LLM` 列入 env 傳遞清單但不 hardcode 值；未設定時容器 SHALL 正常啟動，FUBON fetcher 會在執行時回 `credentials_missing` 的明確錯誤。

#### Scenario: 未設 FUBON env 的 compose up

- **WHEN** 使用者 `.env` 完全沒有 `FUBON_*` 變數，執行 `docker compose up -d`
- **THEN** 所有 7 個 services SHALL 正常 healthy，backend SHALL 正常提供其他銀行的 pipeline
