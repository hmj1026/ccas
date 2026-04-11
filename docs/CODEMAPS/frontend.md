<!-- Generated: 2026-04-11 | Files scanned: 23 | Token estimate: ~500 -->

# Frontend

## Stack

React 19, Vite 8, TypeScript 5.9, Tailwind 4.2, shadcn, TanStack React Query 5, React Router 7

## Page Tree

| Route | Page | Description |
|-------|------|-------------|
| `/login` | `login.tsx` | Token-based authentication |
| `/` | `overview.tsx` | Dashboard: summary cards, upcoming bills |
| `/transactions` | `transactions.tsx` | Filterable list, pagination, CSV export |
| `/analytics` | `analytics.tsx` | Charts: trends, categories, banks |
| `/bills` | `bills.tsx` | Bill list, mark paid, PDF download |
| `/settings` | `settings.tsx` | Bank config, category keyword rules |

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
├── auth-guard.tsx        Session verification HOC
├── layout.tsx            Sidebar navigation shell
├── shared/states.tsx     LoadingState, ErrorState, EmptyState
├── shared/filter-bar.tsx Shared month/bank/status filter controls
└── ui/button.tsx         shadcn button
```

## State Management

- **Server state**: TanStack React Query (caching, refetch, invalidation)
- **Auth**: Cookie-based session (`credentials: 'include'`)
- **Local state**: React hooks only (no Redux/Zustand)

## API Client

`lib/api-client.ts` -- unified fetch wrapper: `apiGet`, `apiPost`, `apiPatch`, `apiDelete`

## Types

`lib/types.ts` -- TypeScript interfaces matching backend Pydantic schemas
