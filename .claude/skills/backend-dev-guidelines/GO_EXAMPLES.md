# Go Backend Examples

## Table of Contents

- [Project Structure](#project-structure)
- [Dependency Injection](#dependency-injection)
- [Handler](#handler)
- [Service](#service)
- [Repository](#repository)
- [Error Handling](#error-handling)
- [Validation](#validation)
- [Middleware](#middleware)
- [Structured Logging](#structured-logging)
- [Configuration](#configuration)
- [Health Checks](#health-checks)
- [Graceful Shutdown](#graceful-shutdown)
- [Dockerfile](#dockerfile)

---

## Project Structure

```
chat-service/
├── cmd/
│   └── main.go              # Entrypoint — wiring, startup, shutdown
├── internal/
│   ├── handler/
│   │   └── user_handler.go  # HTTP handlers
│   ├── service/
│   │   └── user_service.go  # Business logic
│   ├── repository/
│   │   └── user_repo.go     # Database access
│   ├── model/
│   │   └── user.go          # Domain types
│   ├── middleware/
│   │   └── auth.go          # Middleware
│   └── config/
│       └── config.go        # Configuration
├── go.mod
└── go.sum
```

---

## Dependency Injection

```go
// cmd/main.go
func main() {
    cfg := config.Load()

    db, err := sql.Open("postgres", cfg.DatabaseURL)
    if err != nil {
        log.Fatal("failed to connect to database", "error", err)
    }
    defer db.Close()

    // Build dependency chain: repo → service → handler
    userRepo := repository.NewUserRepository(db)
    userService := service.NewUserService(userRepo)
    userHandler := handler.NewUserHandler(userService)

    router := http.NewServeMux()
    userHandler.RegisterRoutes(router)
}
```

---

## Handler

```go
// internal/handler/user_handler.go
type UserHandler struct {
    userService service.UserService // interface, not concrete type
}

func NewUserHandler(us service.UserService) *UserHandler {
    return &UserHandler{userService: us}
}

func (h *UserHandler) CreateUser(w http.ResponseWriter, r *http.Request) {
    // 1. Parse input
    var req CreateUserRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "INVALID_JSON", "Invalid request body")
        return
    }

    // 2. Validate format (transport-level)
    if req.Email == "" {
        writeError(w, http.StatusBadRequest, "VALIDATION_FAILED", "Email is required")
        return
    }

    // 3. Call service (no business logic here)
    user, err := h.userService.CreateUser(r.Context(), req.Email, req.Name)
    if err != nil {
        // 4. Map domain errors to HTTP responses
        handleServiceError(w, err)
        return
    }

    // 5. Format output
    writeJSON(w, http.StatusCreated, user)
}
```

---

## Service

```go
// internal/service/user_service.go

// Interface — defined by the consumer (service layer)
type UserService interface {
    CreateUser(ctx context.Context, email, name string) (*model.User, error)
    GetUser(ctx context.Context, id string) (*model.User, error)
}

type userService struct {
    userRepo repository.UserRepository // interface, not concrete
}

func NewUserService(repo repository.UserRepository) UserService {
    return &userService{userRepo: repo}
}

func (s *userService) CreateUser(ctx context.Context, email, name string) (*model.User, error) {
    // Business validation
    existing, err := s.userRepo.FindByEmail(ctx, email)
    if err != nil {
        return nil, fmt.Errorf("checking existing user: %w", err)
    }
    if existing != nil {
        return nil, ErrUserAlreadyExists
    }

    user := &model.User{
        ID:    uuid.New().String(),
        Email: email,
        Name:  name,
    }

    if err := s.userRepo.Create(ctx, user); err != nil {
        return nil, fmt.Errorf("creating user: %w", err)
    }

    return user, nil
}
```

---

## Repository

```go
// internal/repository/user_repo.go

// Interface — defined here, implemented by concrete type
type UserRepository interface {
    Create(ctx context.Context, user *model.User) error
    FindByID(ctx context.Context, id string) (*model.User, error)
    FindByEmail(ctx context.Context, email string) (*model.User, error)
}

type postgresUserRepo struct {
    db *sql.DB
}

func NewUserRepository(db *sql.DB) UserRepository {
    return &postgresUserRepo{db: db}
}

func (r *postgresUserRepo) FindByEmail(ctx context.Context, email string) (*model.User, error) {
    var user model.User
    // Always use parameterized queries — never string concatenation
    err := r.db.QueryRowContext(ctx,
        "SELECT id, email, name FROM users WHERE email = $1", email,
    ).Scan(&user.ID, &user.Email, &user.Name)

    if errors.Is(err, sql.ErrNoRows) {
        return nil, nil // not found is not an error
    }
    if err != nil {
        return nil, fmt.Errorf("querying user by email: %w", err)
    }
    return &user, nil
}
```

---

## Error Handling

```go
// internal/service/errors.go
var (
    ErrUserNotFound      = errors.New("user not found")
    ErrUserAlreadyExists = errors.New("user already exists")
)

// internal/handler/errors.go
func handleServiceError(w http.ResponseWriter, err error) {
    switch {
    case errors.Is(err, service.ErrUserNotFound):
        writeError(w, http.StatusNotFound, "RESOURCE_NOT_FOUND", "User not found")
    case errors.Is(err, service.ErrUserAlreadyExists):
        writeError(w, http.StatusConflict, "RESOURCE_ALREADY_EXISTS", "Email already registered")
    default:
        slog.Error("unexpected error", "error", err)
        writeError(w, http.StatusInternalServerError, "INTERNAL_ERROR", "Something went wrong")
    }
}
```

---

## Validation

```go
// Handler validates format
func (h *UserHandler) CreateUser(w http.ResponseWriter, r *http.Request) {
    var req CreateUserRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        writeError(w, http.StatusBadRequest, "INVALID_JSON", "Invalid request body")
        return
    }
    if req.Email == "" || req.Name == "" {
        writeError(w, http.StatusBadRequest, "VALIDATION_FAILED", "Email and name are required")
        return
    }

    // Service validates business rules (email uniqueness, etc.)
    user, err := h.userService.CreateUser(r.Context(), req.Email, req.Name)
    // ...
}
```

---

## Middleware

```go
// internal/middleware/request_id.go
func RequestID(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        id := r.Header.Get("X-Request-ID")
        if id == "" {
            id = uuid.New().String()
        }
        ctx := context.WithValue(r.Context(), requestIDKey, id)
        w.Header().Set("X-Request-ID", id)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}

// internal/middleware/logging.go
func Logging(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        wrapped := &responseWriter{ResponseWriter: w, statusCode: 200}

        next.ServeHTTP(wrapped, r)

        slog.Info("request_completed",
            "method", r.Method,
            "path", r.URL.Path,
            "status", wrapped.statusCode,
            "duration_ms", time.Since(start).Milliseconds(),
            "request_id", middleware.GetRequestID(r.Context()),
        )
    })
}

// Middleware chain in main.go
handler := middleware.RequestID(
    middleware.Logging(
        middleware.Auth(router),
    ),
)
```

---

## Structured Logging

```go
// Use slog (Go 1.21+)
import "log/slog"

// Setup in main.go
logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
slog.SetDefault(logger)

// Usage in service
slog.Info("user_created",
    "user_id", user.ID,
    "email", user.Email,
)

slog.Error("failed_to_create_user",
    "error", err,
    "email", email,
)
```

---

## Configuration

```go
// internal/config/config.go
type Config struct {
    Port        string `env:"PORT" default:"8080"`
    DatabaseURL string `env:"DATABASE_URL,required"`
    RedisURL    string `env:"REDIS_URL,required"`
    SecretKey   string `env:"SECRET_KEY,required"`
    LogLevel    string `env:"LOG_LEVEL" default:"info"`
}

func Load() *Config {
    cfg := &Config{
        Port:        getEnvOrDefault("PORT", "8080"),
        DatabaseURL: mustGetEnv("DATABASE_URL"),
        RedisURL:    mustGetEnv("REDIS_URL"),
        SecretKey:   mustGetEnv("SECRET_KEY"),
        LogLevel:    getEnvOrDefault("LOG_LEVEL", "info"),
    }
    return cfg
}

func mustGetEnv(key string) string {
    val := os.Getenv(key)
    if val == "" {
        log.Fatalf("required environment variable %s is not set", key)
    }
    return val
}
```

---

## Health Checks

```go
// Liveness — is the process running?
func (h *HealthHandler) Liveness(w http.ResponseWriter, r *http.Request) {
    writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// Readiness — can it serve traffic?
func (h *HealthHandler) Readiness(w http.ResponseWriter, r *http.Request) {
    checks := map[string]string{}

    if err := h.db.PingContext(r.Context()); err != nil {
        checks["database"] = "failed"
        writeJSON(w, http.StatusServiceUnavailable, map[string]any{
            "status": "not_ready", "checks": checks,
        })
        return
    }
    checks["database"] = "ok"

    writeJSON(w, http.StatusOK, map[string]any{
        "status": "ready", "checks": checks,
    })
}
```

---

## Graceful Shutdown

```go
// cmd/main.go
srv := &http.Server{Addr: ":" + cfg.Port, Handler: handler}

go func() {
    slog.Info("server_starting", "port", cfg.Port)
    if err := srv.ListenAndServe(); err != http.ErrServerClosed {
        log.Fatalf("server error: %v", err)
    }
}()

// Wait for interrupt signal
quit := make(chan os.Signal, 1)
signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
<-quit

slog.Info("shutting_down")

ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

if err := srv.Shutdown(ctx); err != nil {
    slog.Error("shutdown_error", "error", err)
}

db.Close()
slog.Info("shutdown_complete")
```

---

## Dockerfile

```dockerfile
# Build stage
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o server ./cmd/

# Production stage
FROM alpine:3.19
RUN apk --no-cache add ca-certificates && apk upgrade
RUN adduser -D -u 1001 appuser
USER appuser
WORKDIR /app
COPY --from=builder /app/server .
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/healthz || exit 1
ENTRYPOINT ["./server"]
```
