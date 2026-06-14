"""跨模組共用常數（避免 api router 反向依賴 classifier 模組）。"""

# 分類引擎無命中時寫入 Transaction.category 的值；analytics / bot 的彙總查詢
# 也以此作為 NULL category 的 coalesce fallback，確保兩條路徑產生的「未分類」
# 群組名稱一致（SSOT，R19）。
DEFAULT_CATEGORY = "未分類"
