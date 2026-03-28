# React + TypeScript Examples

## Table of Contents

- [Component Structure](#component-structure)
- [Presentational Component](#presentational-component)
- [Container Component](#container-component)
- [Custom Hook](#custom-hook)
- [API Service](#api-service)
- [Data Fetching with Hook](#data-fetching-with-hook)
- [State Management](#state-management)
- [Form Handling](#form-handling)
- [Composition Pattern](#composition-pattern)
- [Error Boundary](#error-boundary)
- [Performance Optimization](#performance-optimization)
- [Component Testing](#component-testing)

---

## Component Structure

```
src/components/UserCard/
├── UserCard.tsx          # Component implementation
├── UserCard.test.tsx     # Tests
├── UserCard.module.css   # Scoped styles (if using CSS Modules)
└── index.ts              # Public export
```

```tsx
// index.ts — clean public API
export { UserCard } from './UserCard';
export type { UserCardProps } from './UserCard';
```

---

## Presentational Component

```tsx
// components/UserCard/UserCard.tsx
interface UserCardProps {
  name: string;
  email: string;
  avatarUrl?: string;
  variant?: 'compact' | 'full';
  onEdit?: () => void;
}

export function UserCard({
  name,
  email,
  avatarUrl,
  variant = 'full',
  onEdit,
}: UserCardProps) {
  return (
    <article className={`user-card user-card--${variant}`}>
      {avatarUrl && <img src={avatarUrl} alt={`${name}'s avatar`} />}
      <h3>{name}</h3>
      <p>{email}</p>
      {onEdit && (
        <button onClick={onEdit} aria-label={`Edit ${name}`}>
          Edit
        </button>
      )}
    </article>
  );
}
```

**Key patterns:**
- Props are typed with an interface (not `any`)
- Destructured with defaults in the signature
- Optional callback (`onEdit`) conditionally renders the button
- Accessibility: `alt` text, `aria-label`

---

## Container Component

```tsx
// pages/UsersPage.tsx
import { useUsers } from '../hooks/useUsers';
import { UserCard } from '../components/UserCard';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { ErrorMessage } from '../components/ErrorMessage';

export function UsersPage() {
  const { users, isLoading, error } = useUsers();

  // Handle all three states
  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage message={error.message} />;
  if (users.length === 0) return <p>No users found.</p>;

  return (
    <section>
      <h1>Users</h1>
      <ul role="list">
        {users.map((user) => (
          <li key={user.id}>
            <UserCard name={user.name} email={user.email} />
          </li>
        ))}
      </ul>
    </section>
  );
}
```

**Key patterns:**
- No data fetching logic — delegated to `useUsers` hook
- Handles loading, error, empty, and success states
- Uses stable `key` (user.id, not index)

---

## Custom Hook

```tsx
// hooks/useDebounce.ts
import { useState, useEffect } from 'react';

export function useDebounce<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delayMs);
    return () => clearTimeout(timer);  // cleanup on value change
  }, [value, delayMs]);

  return debouncedValue;
}

// Usage
function SearchPage() {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 300);
  const { results } = useSearchResults(debouncedQuery);
  // ...
}
```

---

## API Service

```tsx
// services/api.ts
const BASE_URL = import.meta.env.VITE_API_URL;

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      body.error?.code ?? 'UNKNOWN_ERROR',
      body.error?.message ?? 'Something went wrong',
    );
  }

  return response.json();
}

// services/userService.ts
import { request } from './api';

export interface User {
  id: string;
  name: string;
  email: string;
}

export const userService = {
  list: () => request<{ data: User[] }>('/users'),
  getById: (id: string) => request<User>(`/users/${id}`),
  create: (data: { name: string; email: string }) =>
    request<User>('/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
```

**Key patterns:**
- Central `request` function handles auth headers and error parsing
- Typed return values — no `any`
- Service methods are simple, thin wrappers

---

## Data Fetching with Hook

```tsx
// hooks/useUsers.ts
import { useState, useEffect } from 'react';
import { userService, User } from '../services/userService';

interface UseUsersResult {
  users: User[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}

export function useUsers(): UseUsersResult {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await userService.list();
      setUsers(response.data);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch users'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return { users, isLoading, error, refetch: fetchUsers };
}

// With TanStack Query (preferred for production)
import { useQuery } from '@tanstack/react-query';

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => userService.list().then((r) => r.data),
  });
}
```

---

## State Management

### Local State

```tsx
// Simple UI state — useState
function Accordion({ title, children }: AccordionProps) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setIsOpen(!isOpen)}>{title}</button>
      {isOpen && <div>{children}</div>}
    </div>
  );
}
```

### Complex Local State — useReducer

```tsx
interface FormState {
  values: { email: string; password: string };
  errors: Record<string, string>;
  isSubmitting: boolean;
}

type FormAction =
  | { type: 'SET_FIELD'; field: string; value: string }
  | { type: 'SET_ERRORS'; errors: Record<string, string> }
  | { type: 'SUBMIT_START' }
  | { type: 'SUBMIT_END' };

function formReducer(state: FormState, action: FormAction): FormState {
  switch (action.type) {
    case 'SET_FIELD':
      return { ...state, values: { ...state.values, [action.field]: action.value } };
    case 'SET_ERRORS':
      return { ...state, errors: action.errors };
    case 'SUBMIT_START':
      return { ...state, isSubmitting: true };
    case 'SUBMIT_END':
      return { ...state, isSubmitting: false };
  }
}
```

### Global State — Context

```tsx
// store/AuthContext.tsx
interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  const value = {
    user,
    isAuthenticated: user !== null,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
```

---

## Form Handling

```tsx
// components/LoginForm.tsx
interface LoginFormProps {
  onSubmit: (email: string, password: string) => Promise<void>;
}

export function LoginForm({ onSubmit }: LoginFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    if (!email) errs.email = 'Email is required';
    if (!password) errs.password = 'Password is required';
    if (password && password.length < 8) errs.password = 'Password must be 8+ characters';
    return errs;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const validationErrors = validate();
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }
    setIsSubmitting(true);
    try {
      await onSubmit(email, password);
    } catch {
      setErrors({ form: 'Login failed. Please try again.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate>
      <label htmlFor="email">Email</label>
      <input
        id="email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onBlur={() => setErrors(validate())}
        aria-invalid={!!errors.email}
        aria-describedby={errors.email ? 'email-error' : undefined}
      />
      {errors.email && <span id="email-error" role="alert">{errors.email}</span>}

      <label htmlFor="password">Password</label>
      <input
        id="password"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        onBlur={() => setErrors(validate())}
        aria-invalid={!!errors.password}
      />
      {errors.password && <span role="alert">{errors.password}</span>}

      {errors.form && <div role="alert">{errors.form}</div>}

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Logging in...' : 'Log in'}
      </button>
    </form>
  );
}
```

**Key patterns:**
- Validate on blur and on submit
- Shows all errors at once
- Disables button while submitting
- Preserves form state on error
- Accessible: labels, aria-invalid, aria-describedby, role="alert"

---

## Composition Pattern

```tsx
// Compound component pattern
interface TabsProps {
  children: React.ReactNode;
  defaultTab?: string;
}

function Tabs({ children, defaultTab }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab ?? '');

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div role="tablist">{children}</div>
    </TabsContext.Provider>
  );
}

function Tab({ id, label, children }: { id: string; label: string; children: React.ReactNode }) {
  const { activeTab, setActiveTab } = useContext(TabsContext);
  return (
    <>
      <button role="tab" aria-selected={activeTab === id} onClick={() => setActiveTab(id)}>
        {label}
      </button>
      {activeTab === id && <div role="tabpanel">{children}</div>}
    </>
  );
}

// Usage — clean, composable
<Tabs defaultTab="profile">
  <Tab id="profile" label="Profile">
    <ProfileForm />
  </Tab>
  <Tab id="settings" label="Settings">
    <SettingsForm />
  </Tab>
</Tabs>
```

---

## Error Boundary

```tsx
// components/ErrorBoundary.tsx
interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <p>Something went wrong.</p>;
    }
    return this.props.children;
  }
}

// Usage
<ErrorBoundary fallback={<p>Failed to load user profile.</p>}>
  <UserProfile />
</ErrorBoundary>
```

---

## Performance Optimization

```tsx
// React.memo — only when a component re-renders unnecessarily
const ExpensiveList = React.memo(function ExpensiveList({ items }: { items: Item[] }) {
  return (
    <ul>
      {items.map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  );
});

// useMemo — expensive computation
function Dashboard({ transactions }: { transactions: Transaction[] }) {
  const totalRevenue = useMemo(
    () => transactions.reduce((sum, t) => sum + t.amount, 0),
    [transactions],
  );
  return <p>Total: ${totalRevenue}</p>;
}

// useCallback — stable reference for memoized children
function ParentComponent() {
  const [count, setCount] = useState(0);
  const handleClick = useCallback(() => {
    setCount((c) => c + 1);
  }, []);

  return <MemoizedChild onClick={handleClick} />;
}

// Lazy loading — code split at route level
const SettingsPage = React.lazy(() => import('./pages/SettingsPage'));

function App() {
  return (
    <Suspense fallback={<LoadingSpinner />}>
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Suspense>
  );
}
```

---

## Component Testing

```tsx
// components/UserCard/UserCard.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UserCard } from './UserCard';

describe('UserCard', () => {
  it('renders user name and email', () => {
    render(<UserCard name="Alice" email="alice@example.com" />);

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('calls onEdit when edit button is clicked', async () => {
    const onEdit = vi.fn();
    render(<UserCard name="Alice" email="alice@example.com" onEdit={onEdit} />);

    await userEvent.click(screen.getByRole('button', { name: /edit alice/i }));
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it('does not render edit button when onEdit is not provided', () => {
    render(<UserCard name="Alice" email="alice@example.com" />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders avatar when avatarUrl is provided', () => {
    render(<UserCard name="Alice" email="a@b.com" avatarUrl="/avatar.png" />);

    expect(screen.getByAltText("Alice's avatar")).toHaveAttribute('src', '/avatar.png');
  });
});

// Testing with mocked API
import { rest } from 'msw';
import { setupServer } from 'msw/node';

const server = setupServer(
  rest.get('/api/users', (req, res, ctx) =>
    res(ctx.json({ data: [{ id: '1', name: 'Alice', email: 'a@b.com' }] })),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('UsersPage', () => {
  it('renders users after loading', async () => {
    render(<UsersPage />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(await screen.findByText('Alice')).toBeInTheDocument();
  });

  it('shows error when API fails', async () => {
    server.use(rest.get('/api/users', (req, res, ctx) => res(ctx.status(500))));

    render(<UsersPage />);
    expect(await screen.findByText(/something went wrong/i)).toBeInTheDocument();
  });
});
```

**Key patterns:**
- Use `screen.getByRole` / `getByText` — not `container.querySelector`
- Test user interactions with `userEvent`, not `fireEvent`
- Mock the API (MSW), not the hooks
- Test all states: loading, error, empty, success
