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

## Component Patterns

- **Functional components only**: No class components
- **Named exports**: `export function ComponentName()` (not default export)
- **File naming**: PascalCase for components (`BillsPage.tsx`), camelCase for utilities (`utils.ts`)
- **Path aliases**: Use `@/` prefix for imports (e.g., `@/components/ui/button`)

## shadcn/ui

- UI primitives live in `src/components/ui/`
- Add new components via `pnpm dlx shadcn@latest add <component>`
- Do not modify `src/components/ui/` files directly; create wrappers if customization is needed
- Icon library: `lucide-react`

## State Management

- **Server state**: TanStack React Query (`useQuery`, `useMutation`)
- **Local state**: `useState` / `useReducer` for component-local state
- No global state library; lift state or use React Context when needed

## Styling

- **Tailwind CSS**: Use utility classes directly; avoid custom CSS unless necessary
- **CSS variables**: Defined in `src/index.css` for theming
- **Responsive**: Mobile-first approach with Tailwind breakpoints
- **`cn()` helper**: Use `cn()` from `@/lib/utils` for conditional class merging

## Testing

- Test files: `*.test.tsx` / `*.test.ts` colocated with source
- Use `vitest` (not jest) APIs: `describe`, `it`, `expect`, `vi.fn()`
- Use `@testing-library/react` for component tests: `render`, `screen`, `userEvent`
- Avoid testing implementation details; test user-visible behavior

## API Integration

- API calls go through `src/lib/api.ts`
- Backend proxy: Vite dev server proxies `/api` to `http://127.0.0.1:8000`
- No `VITE_API_BASE` needed for development
- Use React Query for all data fetching (caching, refetching, error handling)

## Conventions

- User-facing text in **Traditional Chinese** (正體中文)
- Code comments and variable names in English
- Avoid `any` type; use `unknown` and narrow with type guards
- Prefer `interface` over `type` for object shapes
- Destructure props in function parameters
