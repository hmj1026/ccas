<!-- Generated: 2026-04-22 | Files scanned: 28 | Token estimate: ~550 -->

# Frontend

## Stack

React 19, Vite 8, TypeScript 5.9, Tailwind 4.2, shadcn, TanStack React Query 5, React Router 7

## Page Tree

| Route | Page (LOC) | Description |
|-------|------------|-------------|
| `/login` | `login.tsx` (101) | Token-based authentication |
| `/` | `overview.tsx` (155) | Dashboard: summary cards, upcoming bills |
| `/transactions` | `transactions.tsx` (187) | Filterable list, pagination, CSV export |
| `/analytics` | `analytics.tsx` (240) | Charts: trends, categories, banks |
| `/bills` | `bills.tsx` (281) | Bill list, mark paid, PDF download, expandable transaction detail |
| `/settings` | `settings.tsx` (239) | Bank config, category keyword rules |

## Component Hierarchy

```
App (QueryClient + BrowserRouter)
└── AuthGuard (session check)
    └── Layout (sidebar nav)
        └── Suspense (LoadingState fallback)
            └── <Page /> (React.lazy code-split)
```

## Code Splitting

5 pages lazy-loaded via `React.lazy()` + `<Suspense fallback={<LoadingState />}>`:
`overview`, `transactions`, `analytics`, `bills`, `settings`

## Shared Components

```
components/
├── auth-guard.tsx               Session verification HOC (44)
├── layout.tsx                   Sidebar navigation shell (126)
├── staged-attachments-warning.tsx  Warning panel for failed attachments (157)
├── shared/
│   ├── filter-bar.tsx           Month/bank/status filter controls (227)
│   └── states.tsx               LoadingState, ErrorState, EmptyState (46)
└── ui/
    ├── button.tsx               shadcn button (72)
    ├── dialog.tsx               shadcn dialog / modal (158)
    └── collapsible.tsx          Collapsible expand/collapse (25) — used by bills page
```

## State Management

- **Server state**: TanStack React Query (caching, refetch, invalidation)
- **Auth**: Cookie-based session (`credentials: 'include'`)
- **Local state**: React hooks only (no Redux/Zustand)

## API Client

`lib/api-client.ts` (157) — unified fetch wrapper:
`apiGet`, `apiPost`, `apiPatch`, `apiDelete`, `apiFetchBlob` (PDF/binary download)

## Types

`lib/types.ts` (194) — TypeScript interfaces matching backend Pydantic schemas:
`OverviewData`, `TransactionItem`, `BillItem`, `CategoryKeywordItem`, `BankConfigItem`, `StagedAttachmentItem`, `PaginatedResponse<T>`
