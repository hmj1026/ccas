# ccas gh cli 無法正確推送 commit 修正方案

## 方案選項

### 問題一：憑證讀取失敗 (Keychain -25308) 方案

| 方案 | 描述 | 優點 | 風險/缺點 | 影響範圍 | 測試需求 |
|------|------|------|-----------|----------|----------|
| **A-1** | 確保本機 Keychain 已解鎖（僅限互動式 Terminal） | 無須更改任何 Git 設定。 | 在無 GUI 或非互動式環境中（如 API、mcp 沙盒）無效。 | 無影響。 | 再次手動執行 `git push`。 |
| **A-2** (推薦) | 將 ccas 專案本地 Git credential helper 改為 `gh` | 繞過 macOS `osxkeychain` 存取限制，直接使用 `gh` 的 OAuth Token 進行認證，可於非互動式環境運作。 | 需依賴已安裝且登入的 `gh` CLI。 | 僅限 ccas 本地 repository 設定。 | 測試 `git push --dry-run` 不再出現 `-25308` 錯誤。 |

### 問題二：Pre-push hook 攔截 (Plugin drifted) 方案

| 方案 | 描述 | 優點 | 風險/缺點 | 影響範圍 | 測試需求 |
|------|------|------|-----------|----------|----------|
| **B-1** (推薦) | 執行 `./scripts/verify-claude-plugins.sh --update` 更新 pin 檔 | 與本地實際的 plugin 開發狀態保持一致，一勞永逸。 | 需額外提交一個 `plugin-pins.json` 的 commit。 | 專案的 plugin 版本鎖定檔。 | 執行 `git push --dry-run` 可通過 pre-push hook。 |
| **B-2** | 回滾本地 plugin 的 HEAD 至 pins 鎖定的 commit | 不需要更動專案內的任何檔案或提交新 commit。 | 本地的 `openai-codex` 插件會被切換至舊版本，可能遺失最新更新。 | 僅影響本地的 Claude 插件目錄。 | 執行 `git push --dry-run` 可通過 pre-push hook。 |

## 判斷依據
- **-25308 錯誤**是由於 macOS Keychain 在非互動式環境下被拒絕存取導致。在當前 sandbox 下，將本地 `credential.helper` 設定為 `gh` 提供的 git-credential 能在不影響全域設定的情況下解決認證阻礙。
- **Plugin drift 錯誤**是因為本地的 `openai-codex` 已前進至較新的 commit `db52e28f`，而專案 `plugin-pins.json` 仍停留在 `80c31f99`。如果目前要推送的 commit 需要這項變更，應採用 **B-1** 來更新專案 pin。

## 推薦方案
1. 針對認證問題，推薦採用 **A-2**：在本地專案目錄下設定 local credential helper 使用 `gh` 的憑證服務。
2. 針對 Hook 攔截，推薦採用 **B-1**：更新 `.claude/plugin-pins.json` 至最新的 commit，並進行 commit。

## 後續行動

### 執行步驟：
1. **修復認證問題 (A-2)**：
   ```bash
   git config --local --unset-all credential.helper
   git config --local --add credential.helper ""
   git config --local --add credential.helper "!gh auth git-credential"
   ```
2. **更新 Plugin Pins (B-1)**：
   ```bash
   ./scripts/verify-claude-plugins.sh --update
   ```
3. **提交更新**：
   ```bash
   git add .claude/plugin-pins.json
   git commit -m "chore(plugins): update openai-codex pin to match local version"
   ```
4. **重新推送**：
   ```bash
   git push
   ```

