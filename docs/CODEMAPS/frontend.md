<!-- Verified: 2026-09-10 | Canonical details: ../current-implementation.md -->

# Frontend

> 先看 [目前實作總覽](./current-implementation.md) 取得全局流程；本文件只保留
> 前端路由、元件、狀態與型別的細節。

## Stack

React, Vite, TypeScript, Tailwind CSS, shadcn, TanStack React Query, React Router；版本以 `frontend/package.json` 與 lockfile 為準。

## Page Tree

| Route | Page | Description |
|-------|------|-------------|
| `/login` | `login.tsx` | Token-based authentication |
| `/overview` | `overview.tsx` | Dashboard：summary cards、upcoming bills、budget alert banner |
| `/transactions` | `transactions.tsx` | Filterable list、pagination、CSV/Excel export dialog |
| `/transactions/:id` | `transaction-detail.tsx` | Transaction edit：category override、tags、merchant alias、note |
| `/insights` | `insights.tsx` | Insights v2：bank/year compare、top merchants、comparison-chart |
| `/analytics` | — | redirect → `/insights`（保留舊路徑） |
| `/bills` | `bills.tsx` | Bill list、mark paid、PDF download、expandable inline transactions |
| `/operations` | `operations.tsx` | Pipeline 觸發 + run 列表 + stage 進度即時輪詢 |
| `/settings` | `settings.tsx` | Bank config、category keyword rules |
| `/settings/reminders` | `settings-reminders.tsx` | 每張帳單的 reminder days_before / channel |
| `/settings/budgets` | `settings-budgets.tsx` | 預算 CRUD + scope（monthly_total / monthly_category / monthly_bank） |
| `/settings/rules` | `settings-rules.tsx` | ClassificationRule CRUD + dry-run test |
| `/setup` | `setup/layout.tsx` | Setup wizard shell；redirect → `/setup/gmail` |
| `/setup/gmail` | `setup/gmail.tsx` | OAuth 流程：上傳 client secret → 授權 → status |
| `/setup/gmail/callback` | `setup/gmail-callback.tsx` | OAuth code 接收頁，回填到 `/setup/gmail` |
| `/setup/banks` | `setup/banks.tsx` | 啟用 / 停用銀行 + 顯示名稱 |
| `/setup/secrets` | `setup/secrets.tsx` | 銀行 PDF 密碼寫入（含 `import-from-env`） |
| `/setup/login-credentials` | `setup/login-credentials.tsx` | 銀行網銀登入憑證管理 |
| `/setup/admin` | `setup/admin.tsx` | API token rotate / token-info |

## Component Hierarchy

```
App (QueryClient + BrowserRouter)
└── AuthGuard (session check, all routes except /login)
    └── Layout (sidebar nav)
        └── Suspense (LoadingState fallback)
            └── <Page /> (React.lazy code-split)
                └── /setup/* 子層使用 SetupLayout（獨立 wizard nav）
```

## Code Splitting

17 route modules lazy-loaded via `React.lazy()` + `<Suspense fallback={<LoadingState />}>`：
`overview`、`transactions`、`transaction-detail`、`insights`、`bills`、`operations`、`settings`、`settings-reminders`、`settings-budgets`、`settings-rules`、`setup/layout`、`setup/gmail`、`setup/gmail-callback`、`setup/banks`、`setup/secrets`、`setup/login-credentials`、`setup/admin`

## Shared Components

```
components/
├── auth-guard.tsx                  Session verification HOC
├── layout.tsx                      Sidebar navigation shell
├── staged-attachments-warning.tsx  Warning panel for failed attachments
├── budget-alert-banner.tsx         Active budget breach banner（overview 頂端）
├── budget-progress-card.tsx        Per-budget 進度條 + 警戒色
├── comparison-chart.tsx            Insights bank/year compare 共用圖表
├── export-dialog.tsx               CSV/Excel export 互動 dialog
├── top-merchants-table.tsx         Insights 排行榜
├── shared/
│   ├── filter-bar.tsx              Month/bank/status filter controls
│   └── states.tsx                  LoadingState, ErrorState, EmptyState
└── ui/
    ├── button.tsx                  shadcn button
    ├── dialog.tsx                  shadcn dialog / modal
    └── collapsible.tsx             Collapsible expand/collapse
```

## State Management

- **Server state**：TanStack React Query（caching、refetch、invalidation）
- **Auth**：Cookie-based session（`credentials: 'include'`）
- **Local state**：React hooks only（無 Redux/Zustand）
- **Polling**：`/operations` 對 `/api/pipeline/runs/{id}` 設定 short interval refetch 直至 status terminal

## API Client

`lib/api-client.ts` — unified fetch wrapper：
`apiGet`、`apiPost`、`apiPatch`、`apiPut`、`apiDelete`、`apiFetchBlob`（PDF/Excel/CSV 二進位下載）

## Types

`lib/types.ts` — TypeScript interfaces 對齊 backend Pydantic schema：
`OverviewData`、`TransactionItem`、`TransactionDetailItem`、`BillItem`、`CategoryKeywordItem`、`BankConfigItem`、`StagedAttachmentItem`、`PipelineRunSummary`、`PipelineRunDetail`、`ClassificationRuleItem`、`BudgetItem`、`BudgetAlertItem`、`BudgetCurrentPeriod`、`ReminderSettingItem`、`BankCompareItem`、`YearCompareItem`、`TopMerchantItem`、`PaginatedResponse<T>`、Setup 系列 (`SetupBankItem`、`BankSecretStatus`、`BankLoginCredentialStatus`、`GmailConnectionStatus`、`AdminTokenInfo`)
