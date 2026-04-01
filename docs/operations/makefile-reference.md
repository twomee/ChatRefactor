# Makefile Reference

All K8s tasks have a `make` shortcut. Run `make <target>` from the project root.

> **Docker Compose targets** (`make build`, `make up`, `make deploy`, `make down`) are documented in [Docker Compose Operations → Section 1](docker-compose.md#1-running-in-production-mode-docker).

## Variables

| Variable | Default | Used By |
|----------|---------|---------|
| `SVC` | *(required for some targets)* | `k8s-logs`, `k8s-shell`, `k8s-restart`, `k8s-redeploy` |
| `OVERLAY` | `dev` | `k8s-deploy`, `k8s-validate` |
| `CLUSTER_NAME` | `chatbox` | All kind commands |

Valid values for `SVC`: `auth-service`, `chat-service`, `message-service`, `file-service`, `frontend`, `kong`

Valid values for `OVERLAY`: `dev`, `staging`, `prod`, `staging-kind`, `prod-kind`

## Cluster Lifecycle

```bash
make k8s-setup-local      # Full zero-to-running setup (kind + infra + build + deploy)
make k8s-teardown         # Tear everything down and delete the kind cluster
```

## Infrastructure

```bash
make k8s-infra-setup      # Install PostgreSQL, Redis, Kafka via Helm
make k8s-infra-teardown   # Uninstall Helm releases (keeps kind cluster)
make k8s-init-jobs        # Run db-init + kafka-init jobs (creates databases and topics)
make k8s-secrets          # Generate K8s Secrets from infra/k8s/secrets.env
```

## Application

```bash
make k8s-build                          # Build all 5 Docker images and load into kind
make k8s-deploy                         # Deploy with dev overlay (default)
make k8s-deploy OVERLAY=staging-kind    # Deploy with a different overlay
make k8s-validate                       # Dry-run YAML validation (no cluster changes)
make k8s-validate OVERLAY=prod          # Validate a specific overlay

make k8s-redeploy SVC=auth-service      # Rebuild image + reload into kind + rolling restart
make k8s-redeploy SVC=chat-service      # Same for chat-service
```

## Operations

```bash
make k8s-status                         # Show pods, services, infra, recent events
make k8s-logs SVC=auth-service          # Tail live logs (all pods for that service)
make k8s-logs SVC=chat-service          # Same for chat-service
make k8s-shell SVC=auth-service         # Open a shell inside a running pod
make k8s-restart SVC=message-service    # Rolling restart (zero downtime)
make k8s-port-forward                   # Print access URLs (NodePort already exposed)
```

## Monitoring

```bash
make k8s-monitoring-setup   # Install Prometheus + Grafana (first time only)
make k8s-grafana            # Print Grafana URL and credentials
make k8s-prometheus         # Port-forward Prometheus → http://localhost:9090
```

---

## Kubernetes Scripts

All scripts live in `infra/k8s/scripts/`. Run them from the project root.

### Before You Run Any Script

**1. Create your secrets file** (first time only):

```bash
cp infra/k8s/base/secrets.env.example infra/k8s/secrets.env
# Edit infra/k8s/secrets.env with your passwords — never commit this file
```

The file contains:

```bash
POSTGRES_PASSWORD=chatbox_pass      # PostgreSQL password for all 4 service databases
REDIS_PASSWORD=chatbox_redis_pass   # Redis auth password
SECRET_KEY=change-this-in-prod      # JWT signing secret (use: openssl rand -hex 32)
ADMIN_USERNAME=admin                # Bootstrap admin user created on first deploy
ADMIN_PASSWORD=changeme             # Bootstrap admin password
```

> If `infra/k8s/secrets.env` is missing, scripts fall back to the insecure example defaults — fine for local dev, never for staging/prod.

---

### Script Reference

| Script | What It Does | Usage |
|--------|-------------|-------|
| `setup-local.sh` | Full setup: creates kind cluster → installs Postgres/Redis/Kafka → generates secrets → runs init jobs → builds images → deploys app | `bash infra/k8s/scripts/setup-local.sh` |
| `teardown.sh` | Removes app, init jobs, Helm releases, monitoring, and deletes the kind cluster | `bash infra/k8s/scripts/teardown.sh` |
| `build-images.sh` | Builds Docker images for all 5 services and loads them into the kind cluster | `bash infra/k8s/scripts/build-images.sh` |
| `deploy.sh` | Applies a Kustomize overlay and waits for all 6 rollouts to complete | `bash infra/k8s/scripts/deploy.sh [overlay]` |
| `generate-secrets.sh` | Creates or updates all K8s Secrets from `infra/k8s/secrets.env`. Reads the actual Redis password from the cluster to work around Bitnami's password-on-upgrade behavior | `bash infra/k8s/scripts/generate-secrets.sh` |

### setup-local.sh

```bash
bash infra/k8s/scripts/setup-local.sh
```

Runs 7 steps in order:
1. Creates kind cluster `chatbox` with NodePorts 30000/30080/30030 — **idempotent**, skips if cluster already exists
2. Creates namespaces: `chatbox`, `chatbox-infra`, `chatbox-monitoring`
3. Installs PostgreSQL v18.5.14 + Redis v25.3.9 via Helm, Kafka via manifest
4. Generates K8s Secrets from `infra/k8s/secrets.env`
5. Runs `db-init` job (creates 4 databases + tables) and `kafka-init` job (creates topics)
6. Builds all 5 Docker images and loads them into kind
7. Deploys with the `dev` overlay + re-applies secrets (Kustomize overwrites them)

### teardown.sh

```bash
bash infra/k8s/scripts/teardown.sh
```

Runs 5 steps in order:
1. Deletes all application resources (dev overlay)
2. Deletes init jobs
3. Uninstalls Redis + PostgreSQL Helm releases, removes Kafka manifest
4. Uninstalls the Prometheus/Grafana monitoring Helm release
5. Deletes the kind cluster

### build-images.sh

```bash
bash infra/k8s/scripts/build-images.sh
```

Builds all 5 images in sequence and loads each into the kind cluster:
- `auth-service:latest` ← `services/auth-service/`
- `chat-service:latest` ← `services/chat-service/`
- `message-service:latest` ← `services/message-service/`
- `file-service:latest` ← `services/file-service/`
- `frontend:latest` ← `frontend/` (with `VITE_API_BASE=http://localhost:30080`)

Run this after code changes, then `make k8s-redeploy SVC=<name>` for a specific service, or `make k8s-deploy` to redeploy everything.

### deploy.sh

```bash
bash infra/k8s/scripts/deploy.sh           # defaults to dev overlay
bash infra/k8s/scripts/deploy.sh dev
bash infra/k8s/scripts/deploy.sh staging-kind   # staging config with local images
bash infra/k8s/scripts/deploy.sh prod-kind      # prod config with local images
bash infra/k8s/scripts/deploy.sh staging        # requires DockerHub images to exist
bash infra/k8s/scripts/deploy.sh prod           # requires DockerHub images to exist
```

Applies `kubectl apply -k infra/k8s/overlays/<overlay>` then waits for all 6 deployments (`auth-service`, `chat-service`, `message-service`, `file-service`, `frontend`, `kong`) to finish rolling out.

### generate-secrets.sh

```bash
bash infra/k8s/scripts/generate-secrets.sh
```

Creates or updates 6 K8s Secrets in the `chatbox` namespace:
- `chatbox-infra-secrets` — shared passwords and JWT key
- `auth-service-secrets`, `chat-service-secrets`, `message-service-secrets`, `file-service-secrets` — per-service `DATABASE_URL`
- `auth-admin-secret` — admin username + password

**Important:** Bitnami Redis v25 ignores `--set auth.password` on `helm upgrade` if the secret already exists. This script reads the actual Redis password from the cluster (`kubectl get secret redis`) so the `REDIS_URL` in the app secrets always matches the real password.

> **E2E Testing:** The e2e test suite has been migrated to pytest. Run `make e2e` to auto-detect the environment, or `make e2e KONG_URL=http://localhost:30080` to target K8s explicitly. See [Makefile Reference — E2E Tests](makefile-reference.md#9-end-to-end-tests) for all available targets.

---

## Monitoring (Grafana + Prometheus)

Install the monitoring stack (first time only):
```bash
make k8s-monitoring-setup
```

### Grafana

```
URL:      http://localhost:30030
Username: admin
Password: admin
```

```bash
# Or open it via make
make k8s-grafana
```

Pre-loaded dashboards (Dashboards → Browse):
- **Kubernetes / Compute Resources / Namespace (Pods)** — CPU and memory per pod
- **Kubernetes / Compute Resources / Cluster** — Cluster-wide resource usage
- **Node Exporter / Nodes** — Host machine metrics

### Prometheus

```bash
# Port-forward to http://localhost:9090
make k8s-prometheus
```

Useful queries in the Prometheus UI:
```promql
# CPU usage per chatbox pod
rate(container_cpu_usage_seconds_total{namespace="chatbox"}[5m])

# Memory per chatbox pod
container_memory_working_set_bytes{namespace="chatbox"}

# Active HTTP requests (if service exposes /metrics)
http_requests_total{namespace="chatbox"}
```

Quick health check (no browser needed):
```bash
make k8s-status                                         # all pods running?
kubectl top pods -n chatbox                             # live CPU/memory
kubectl get events -n chatbox --field-selector type=Warning  # any warnings?
```

## 9. End-to-End Tests

Run the full e2e test suite against whichever environment is running.

| Target | Description |
|--------|-------------|
| `make e2e-setup` | Install Python test dependencies (`pip install -r tests/e2e/requirements.txt`) |
| `make e2e` | Auto-detect environment, run all ~85 tests |
| `make e2e-smoke` | Quick subset (~15 core tests) |
| `make e2e-all` | Run against Docker Compose **and** K8s sequentially |
| `make e2e KONG_URL=http://host:port` | Override auto-detection with explicit URL |
| `make e2e-auth` | Auth service tests only |
| `make e2e-pm` | Private messaging tests only |
| `make e2e-files` | File service tests only |
| `make e2e-chat` | Chat rooms + WebSocket tests only |
| `make e2e-messages` | Message service tests only |
| `make e2e-admin` | Admin dashboard tests only |
| `make e2e-monitoring` | Monitoring tests only (auto-skipped if Grafana unavailable) |

### Default Behavior (No Config)

When you run `make e2e` without any arguments:

1. Checks if **Docker Compose** is running (`localhost:80`) → uses it
2. Else checks if **K8s** is running (`localhost:30080`) → uses it
3. If neither responds → exits with a message telling you to start an environment

### Running Both Environments

If both Docker Compose and K8s are running simultaneously:

```bash
make e2e                                    # hits Docker Compose (port 80 wins)
make e2e KONG_URL=http://localhost:30080     # hits K8s explicitly
make e2e-all                                # runs both sequentially
```
