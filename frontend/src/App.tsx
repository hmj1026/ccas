/**
 * 應用程式根元件。
 *
 * 目前為 Placeholder 頁面，顯示系統名稱與健康狀態。
 * 後續將整合路由與版面配置。
 */
function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900">CCAS</h1>
        <p className="mt-2 text-gray-600">
          Credit Card Artifact System
        </p>
        <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-2">
          <span className="text-green-700">Health: OK</span>
        </div>
      </div>
    </div>
  )
}

export default App
