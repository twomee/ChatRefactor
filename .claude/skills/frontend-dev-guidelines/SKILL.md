---
name: frontend-dev-guidelines
description: Frontend development guidelines covering component design, state management, data fetching, forms, styling, routing, accessibility basics, performance, build tooling, and component testing. Agnostic principles with React and TypeScript examples. Use when writing frontend code, creating components, managing state, fetching data, styling UI, writing component tests, or working on frontend architecture. Triggers on component, hook, state management, data fetching, form handling, styling, CSS, frontend, React, TypeScript, props, context, reducer, useMemo, useEffect, component test, render test, mock API.
---

# Frontend Development Guidelines

## Purpose

Provide implementation-level guidance for building frontend applications that are:
- **Composable** — small, focused components that combine to build complex UIs
- **Predictable** — clear data flow, explicit state ownership, no hidden side effects
- **Testable** — components and logic can be tested in isolation
- **Performant** — renders only what changed, loads only what's needed

**Framework-agnostic principles** with concrete React + TypeScript examples. See reference file for full code:
- [REACT_EXAMPLES.md](REACT_EXAMPLES.md) — React + TypeScript patterns

### Relationship to Other Skills

| Skill | Scope | When to use instead |
|-------|-------|---------------------|
| **architecture** | System-level: SPA vs SSR, micro-frontends, module boundaries | "Should we split the frontend?" |
| **api-design** | Contract-level: what the API returns, error shapes | "What should this endpoint return?" |
| **backend-dev-guidelines** | Server implementation: handlers, services, repos | "How do I write this handler?" |
| **frontend-dev-guidelines** (this) | UI implementation: components, state, data fetching, testing | "How do I build this component?" |

---

## Project Structure

### The Layered Layout

```
src/
├── components/          # Reusable UI components (Button, Modal, Card)
│   └── Button/
│       ├── Button.tsx
│       ├── Button.test.tsx
│       └── index.ts
├── pages/ or views/     # Page-level components (route targets)
├── hooks/               # Custom hooks (useAuth, useDebounce, useFetch)
├── services/            # API calls, external integrations
├── store/ or state/     # Global state management
├── utils/               # Pure utility functions
├── types/               # Shared TypeScript types/interfaces
└── assets/              # Static files (images, fonts, icons)
```

### The Rules

1. **Components don't fetch data or manage global state.** They receive props and render UI.
2. **Hooks encapsulate logic.** Data fetching, subscriptions, and complex state live in hooks.
3. **Services are the only layer that talks to the API.** Components and hooks never call `fetch` directly.
4. **Pages wire things together.** They compose components, connect hooks, and handle routing params.
5. **Utils are pure functions.** No side effects, no imports from components or hooks.

---

## Component Design

### Component Types

| Type | Purpose | State? | Side effects? | Examples |
|------|---------|--------|---------------|---------|
| **Presentational** | Render UI based on props | No (or local UI state only) | No | `Button`, `Card`, `Avatar` |
| **Container** | Wire data to presentational components | Yes (via hooks) | Yes (data fetching) | `UserList`, `DashboardPage` |
| **Layout** | Define page structure | No | No | `Sidebar`, `PageLayout`, `Grid` |

### Composition Over Configuration

```
# BAD — god component with too many props
<DataTable
  data={data}
  sortable={true}
  filterable={true}
  paginated={true}
  onSort={...}
  onFilter={...}
  renderRow={...}
  renderHeader={...}
  emptyState={...}
/>

# GOOD — composed from focused components
<DataTable data={data}>
  <DataTable.Header sortable onSort={...} />
  <DataTable.Body renderRow={...} />
  <DataTable.Pagination pageSize={20} />
  <DataTable.EmptyState>No results found</DataTable.EmptyState>
</DataTable>
```

### Props Guidelines

| Rule | Why |
|------|-----|
| Keep prop count under 7 | More than 7 = component does too much, split it |
| Use children for content | `<Card>{content}</Card>` not `<Card content={...} />` |
| Avoid boolean props for variants | `variant="primary"` not `isPrimary isLarge isOutline` |
| Type all props explicitly | No `any`, no implicit types |
| Default optional props | Don't force consumers to pass everything |

---

## State Management

### Where Does State Belong?

```
Is it used by only one component?
  └── Yes → Local state (useState)

Is it shared between siblings/cousins?
  └── Yes → Lift to nearest common parent

Is it used across many unrelated components?
  └── Yes → Global state (context, store)

Is it server data (fetched from API)?
  └── Yes → Server state (data fetching library)

Is it URL-derived (page, filters, search)?
  └── Yes → URL state (search params, route params)
```

### State Categories

| Category | What it is | Where to put it |
|----------|-----------|-----------------|
| **UI state** | Open/closed, selected tab, hover | `useState` — local to component |
| **Form state** | Input values, validation errors, dirty flags | Form library or `useReducer` |
| **Server state** | Data from API, loading/error states, cache | Data fetching library (TanStack Query, SWR) |
| **Global app state** | Auth user, theme, feature flags | Context or state library (Zustand, Redux) |
| **URL state** | Current page, filters, sort order | Router params + search params |

### Rules

- **Don't duplicate server state in global state.** Use a data fetching library that caches.
- **Don't put everything in global state.** Most state is local or server state.
- **Derive computed values, don't store them.** `const total = items.reduce(...)` not `const [total, setTotal] = useState(...)`.
- **Colocate state with the component that uses it.** Lift up only when needed.

---

## Data Fetching

### The Principle

Separate **what to fetch** (service layer) from **when to fetch** (hooks) from **what to show** (components).

### Data Fetching Flow

```
Service (API call)  →  Hook (manages loading/error/cache)  →  Component (renders data)
```

### Rules

| Rule | Why |
|------|-----|
| Never call `fetch`/`axios` in components | Mixes concerns, untestable, duplicated |
| Centralize API calls in services | One place to change base URL, headers, auth |
| Handle loading, error, and empty states | Every fetch has three outcomes — handle all of them |
| Cache server state | Avoid re-fetching data the user already has |
| Show stale data while refreshing | Better UX than showing a spinner every time |

---

## Forms

### Form Design Principles

| Principle | Why |
|-----------|-----|
| Validate on blur + on submit | Immediate feedback without interrupting typing |
| Show all errors at once | Don't make the user fix one error, submit, find the next |
| Disable submit while submitting | Prevent double submissions |
| Preserve form state on error | Don't clear the form if submission fails |
| Use controlled components | Predictable state, easier to validate and test |

---

## Styling

### Approaches

| Approach | Best for | Trade-off |
|----------|----------|-----------|
| **CSS Modules** | Scoped styles, no runtime cost | Class name management |
| **Tailwind CSS** | Rapid prototyping, consistent design tokens | Long class strings, learning curve |
| **CSS-in-JS** (styled-components) | Dynamic styles based on props | Runtime cost, bundle size |
| **Vanilla CSS with BEM** | Simple projects, no build step | Global scope, naming discipline |

### Rules

- **Never use inline styles for anything beyond dynamic values** (e.g., `style={{ width: dynamicWidth }}`).
- **Use design tokens** (variables) for colors, spacing, typography — not raw values.
- **Keep responsive breakpoints consistent** — define once, use everywhere.
- **Prefer component-scoped styles** — avoid global CSS except for resets and tokens.

---

## Performance

### Render Optimization

| Problem | Solution | When to use |
|---------|----------|-------------|
| Re-rendering on parent render | Memoize component (`React.memo`) | Only when profiling confirms it helps |
| Expensive computation on every render | Memoize value (`useMemo`) | Heavy calculations, not simple derivations |
| Callback identity changes | Memoize callback (`useCallback`) | Only when passing to memoized children |
| Rendering a huge list | Virtualization (react-window, TanStack Virtual) | 100+ items in a list |

### Rules

- **Don't optimize prematurely.** Measure first with DevTools profiler.
- **Memoization has a cost.** The comparison overhead is not free — only memoize when it helps.
- **Code split at the route level.** Lazy-load pages, not individual components.
- **Optimize images.** Use correct format (WebP), correct size, lazy load below fold.

---

## Build & Tooling

### Environment Configuration

| Rule | Why |
|------|-----|
| Use `.env` files for environment-specific config | API URLs, feature flags differ per environment |
| Prefix public env vars | `VITE_` or `NEXT_PUBLIC_` — prevents leaking server secrets |
| Never commit `.env` | Secrets in git are forever |
| Provide `.env.example` | New developers know what to configure |

### Bundle Guidelines

- **Tree-shake imports** — `import { Button } from './components'` not `import * as Components`
- **Analyze bundle size** — use `vite-bundle-analyzer` or `webpack-bundle-analyzer`
- **Set a budget** — fail the build if JS bundle exceeds a threshold (e.g., 250KB gzipped)

---

## Component Testing

### What to Test

| Test this | Don't test this |
|-----------|-----------------|
| User interactions (click, type, submit) | Internal state values |
| Rendered output for given props | Implementation details (hooks called, state shape) |
| Conditional rendering (loading, error, empty) | CSS class names or styles |
| Accessibility (labels, roles, keyboard) | That a library works (React, router) |
| Integration between parent and child | Snapshot tests (fragile, low signal) |

### Testing Principles

| Principle | Why |
|-----------|-----|
| Test behavior, not implementation | Survives refactoring |
| Render like a user sees it | Use `screen.getByRole`, not `container.querySelector` |
| One concept per test | Clear failure messages |
| Mock the API, not the hooks | Test the full component, stub only the network |
| Test accessibility | `getByRole` enforces ARIA, catches a11y regressions |

### Test Structure

```
describe('ComponentName', () => {
  it('renders initial state correctly', () => { ... })
  it('handles user interaction', () => { ... })
  it('shows error state when API fails', () => { ... })
  it('shows empty state when no data', () => { ... })
})
```

---

## Anti-Patterns to Flag

| Anti-pattern | What it looks like | Why it's bad |
|-------------|-------------------|--------------|
| **Prop drilling** | Passing props through 4+ levels | Fragile, hard to refactor — use context or composition |
| **God component** | 300+ line component with mixed concerns | Untestable, un-reusable — split into smaller components |
| **useEffect for everything** | Fetching, subscriptions, derived state all in effects | Race conditions, stale closures — use appropriate patterns |
| **Storing derived state** | `useState` for values computable from other state | State goes out of sync — derive instead |
| **Fetching in components** | `fetch()` inside `useEffect` directly | No caching, no error handling, duplicated — use service + hook |
| **Index as key** | `{items.map((item, i) => <Item key={i} />)}` | Breaks reconciliation on reorder — use stable IDs |
| **Wildcard imports** | `import * as utils from './utils'` | Kills tree-shaking, bundles everything |
| **Ignoring loading/error states** | Only handling the happy path | Broken UX — every async operation has three states |

---

## Quick Reference

```
Frontend Development Checklist:
1. Structure: components / hooks / services / utils (no business logic in components)
2. Components: presentational vs container, composition over configuration, <7 props
3. State: local first, lift when needed, server state in fetch library, derive don't store
4. Data fetching: service → hook → component, handle all three states
5. Forms: validate on blur+submit, show all errors, preserve state on failure
6. Styling: design tokens, component-scoped, responsive breakpoints consistent
7. Performance: measure first, memoize only when proven, code-split routes, lazy images
8. Build: .env per environment, tree-shake, bundle budget
9. Testing: test behavior not implementation, mock API not hooks, test a11y
```

See [REACT_EXAMPLES.md](REACT_EXAMPLES.md) for concrete code.
