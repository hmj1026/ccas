---
paths:
  - "frontend/**/*.ts"
  - "frontend/**/*.tsx"
  - "frontend/**/*.css"
---
# CCAS Frontend Conventions

## Tooling

- **Framework**: React 19 + Vite
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS 4 with CSS variables
- **UI Library**: shadcn/ui (base-nova style) + Lucide icons
- **State**: TanStack React Query for server state
- **Routing**: React Router 7
- **Testing**: Vitest + React Testing Library
- **Linter**: ESLint (typescript-eslint + react hooks/refresh plugins)
- **Package Manager**: pnpm

## CCAS-Specific Patterns

- **Named exports** (no default exports); PascalCase components (`BillsPage.tsx`); `@/` path alias
- **shadcn/ui**: primitives in `src/components/ui/`, install via `pnpm dlx shadcn@latest add <component>`; never edit ui/ files directly — wrap them
- **State**: TanStack React Query for server state; no global state library
- **`cn()` helper** from `@/lib/utils` for conditional class merging
- **API**: all calls via `src/lib/api.ts`; Vite dev proxies `/api` → `http://127.0.0.1:8000`; no `VITE_API_BASE` in dev

## Test Runner Scopes (must distinguish)

- `pnpm test` = Vitest, scoped to `src/**` only (test files colocated as `*.test.tsx`)
- `pnpm e2e` / `pnpm e2e:ui` = Playwright, scoped to `frontend/e2e/`
- When editing `vite.config.ts` / `vitest.config.ts`, preserve `test.include` / `test.exclude` so Vitest does not collect `e2e/**`

## Conventions

- User-facing text in **Traditional Chinese** (正體中文); code/comments in English
- Avoid `any`; use `unknown` + type guards. Prefer `interface` for object shapes

> For generic React/Vite patterns, see ECC `frontend-patterns` skill.
