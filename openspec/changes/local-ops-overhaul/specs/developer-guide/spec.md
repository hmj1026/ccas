## ADDED Requirements

### Requirement: 開發者環境設定指南

系統 SHALL 提供 `docs/developer-guide.md`，面向開發者，涵蓋環境設定、架構總覽、測試、貢獻指南。

#### Scenario: 開發者依文件完成開發環境設定

- **WHEN** 開發者依照 `docs/developer-guide.md` 操作
- **THEN** 文件 SHALL 引導完成：前置需求安裝（Python 3.12、uv、Node.js、pnpm）、clone repo、`.env` 建立、Gmail/Telegram 設定、一鍵啟動（腳本模式）

#### Scenario: 架構總覽章節

- **WHEN** 開發者需要了解專案架構
- **THEN** 文件 SHALL 包含：技術棧、模組結構（pipeline 五階段）、資料流示意、目錄結構說明

#### Scenario: 測試與品質章節

- **WHEN** 開發者需要執行測試或檢查程式碼品質
- **THEN** 文件 SHALL 提供：pytest 執行指令、coverage 報告指令、ruff lint/format 指令、pyright type check 指令

#### Scenario: 貢獻指南

- **WHEN** 開發者需要提交變更
- **THEN** 文件 SHALL 包含：branching 策略、commit message 格式（conventional commits）、PR 流程

### Requirement: Seed data 快速建立測試資料

系統 SHALL 提供 seed data 命令，讓開發者快速建立或重置測試用的帳單和交易資料。

#### Scenario: 建立 seed data

- **WHEN** 開發者執行 seed data 命令
- **THEN** 系統 SHALL 在資料庫中建立測試用 Bill 和 Transaction 記錄

#### Scenario: 重置 seed data

- **WHEN** 開發者執行 seed data 命令加上 `--reset` flag
- **THEN** 系統 SHALL 先清除所有既有的 seed 資料，再重新建立
