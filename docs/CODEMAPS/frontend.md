<!-- Generated: 2026-05-10 | Files scanned: ~50 | Token estimate: ~960 -->

# Frontend

## Stack

React 19, Vite 8, TypeScript 5.9, Tailwind 4.2, shadcn, TanStack React Query 5, React Router 7

## Page Tree

| Route | Page (LOC) | Description |
|-------|------------|-------------|
| `/login` | `login.tsx` (101) | Token-based authentication |
| `/overview` | `overview.tsx` (157) | Dashboard：summary cards、upcoming bills、budget alert banner |
| `/transactions` | `transactions.tsx` (197) | Filterable list、pagination、CSV/Excel export dialog |
| `/transactions/:id` | `transaction-detail.tsx` (368) | Transaction edit：category override、tags、merchant alias、note |
| `/insights` | `insights.tsx` (336) | Insights v2：bank/year compare、top merchants、comparison-chart |
| `/analytics` | — | redirect → `/insights`（保留舊路徑） |
| `/bills` | `bills.tsx` (281) | Bill list、mark paid、PDF download、expandable inline transactions |
| `/operations` | `operations.tsx` (674) | Pipeline 觸發 + run 列表 + stage 進度即時輪詢 |
| `/settings` | `settings.tsx` (252) | Bank config、category keyword rules |
| `/settings/reminders` | `settings-reminders.tsx` (222) | 每張帳單的 reminder days_before / channel |
| `/settings/budgets` | `settings-budgets.tsx` (301) | 預算 CRUD + scope（bank / category / total） |
| `/settings/rules` | `settings-rules.tsx` (466) | ClassificationRule CRUD + dry-run test |
| `/setup` | `setup/layout.tsx` (58) | Setup wizard shell；redirect → `/setup/gmail` |
| `/setup/gmail` | `setup/gmail.tsx` (390) | OAuth 流程：上傳 client secret → 授權 → status |
| `/setup/gmail/callback` | `setup/gmail-callback.tsx` (50) | OAuth code 接收頁，回填到 `/setup/gmail` |
| `/setup/banks` | `setup/banks.tsx` (165) | 啟用 / 停用銀行 + 顯示名稱 |
| `/setup/secrets` | `setup/secrets.tsx` (372) | 銀行 PDF 密碼寫入（含 `import-from-env`） |
| `/setup/admin` | `setup/admin.tsx` (276) | API token rotate / token-info |

## Component Hierarchy

```
App (QueryClient + BrowserRouter)
└── AuthGuard (session check, except /login & /setup/gmail/callback)
    └── Layout (sidebar nav)
        └── Suspense (LoadingState fallback)
            └── <Page /> (React.lazy code-split)
                └── /setup/* 子層使用 SetupLayout（獨立 wizard nav）
```

## Code Splitting

15 pages lazy-loaded via `React.lazy()` + `<Suspense fallback={<LoadingState />}>`：
`overview`、`transactions`、`transaction-detail`、`insights`、`bills`、`operations`、`settings`、`settings-reminders`、`settings-budgets`、`settings-rules`、`setup/layout`、`setup/gmail`、`setup/gmail-callback`、`setup/banks`、`setup/secrets`、`setup/admin`

## Shared Components

```
components/
├── auth-guard.tsx                  Session verification HOC (44)
├── layout.tsx                      Sidebar navigation shell (136)
├── staged-attachments-warning.tsx  Warning panel for failed attachments (157)
├── budget-alert-banner.tsx         Active budget breach banner（overview 頂端） (85)
├── budget-progress-card.tsx        Per-budget 進度條 + 警戒色 (72)
├── comparison-chart.tsx            Insights bank/year compare 共用圖表 (85)
├── export-dialog.tsx               CSV/Excel export 互動 dialog (164)
├── top-merchants-table.tsx         Insights 排行榜 (41)
├── shared/
│   ├── filter-bar.tsx              Month/bank/status filter controls (227)
│   └── states.tsx                  LoadingState, ErrorState, EmptyState (46)
└── ui/
    ├── button.tsx                  shadcn button (72)
    ├── dialog.tsx                  shadcn dialog / modal (158)
    └── collapsible.tsx             Collapsible expand/collapse (25)
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
`OverviewData`、`TransactionItem`、`TransactionDetailItem`、`BillItem`、`CategoryKeywordItem`、`BankConfigItem`、`StagedAttachmentItem`、`PipelineRunSummary`、`PipelineRunDetail`、`ClassificationRuleItem`、`BudgetItem`、`BudgetAlertItem`、`BudgetCurrentPeriod`、`ReminderSettingItem`、`BankCompareItem`、`YearCompareItem`、`TopMerchantItem`、`PaginatedResponse<T>`、Setup 系列 (`SetupBankItem`、`BankSecretStatus`、`GmailConnectionStatus`、`AdminTokenInfo`)
