## Context

User guide 完整性測試（Area 1~7，共 56 個新測試）全數 GREEN，確認程式碼行為正確。但比對過程中發現 `docs/qa-testing-guide.md` 的「已知限制」段落嚴重過時，與系統實際能力不符。此變更僅修正文件，不涉及程式碼。

## Goals / Non-Goals

**Goals:**
- 讓 QA testing guide 的「已知限制」段落反映系統真實狀態
- 更新測試數量為實際值
- 歸檔 e2e walkthrough 中已完成的問題項目

**Non-Goals:**
- 不重寫整份 QA guide（僅修正已確認的過時段落）
- 不新增或修改程式碼
- 不處理 e2e walkthrough #11（FUBON parser can_parse=False）— 需另案調查

## Decisions

1. **直接修改文件而非重新生成** — 變更幅度小（3 處修正 + 1 處狀態更新），直接 patch 比重寫更安全且 diff 可讀。
2. **測試數量使用「1000+」而非精確數字** — 測試數量隨開發持續增長，使用約數避免再次過時。
3. **保留「已知限制」段落結構** — 僅更新內容，移除已解決項目（#1, #4），保留仍有效的限制（#2 OCR 需 Docker、#3 前端無覆蓋率、#5 SQLite 單連線）。

## Risks / Trade-offs

- [Risk] 測試數量再次過時 → 使用「1000+」約數，降低維護頻率
- [Risk] 遺漏其他過時段落 → 本次僅修已確認項目；未來可建立文件自動驗證機制
