# Kubernetes Support for Chatbox — Design Spec & Implementation Plan

## Context

The Chatbox project is a polyglot microservices chat platform currently orchestrated via Docker Compose. This spec adds production-grade Kubernetes support so the project can run locally (kind) and be deployed to any managed K8s service (EKS/GKE/AKS). The design follows industry-standard patterns used at most mid-to-large companies.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target environment | Local (kind) + cloud-ready | Standard portable approach |
| Infrastructure | All in-cluster | Self-contained, portable |
| App manifests | Kustomize (base + overlays) | Industry standard for own services, real YAML |
| Infra deployment | Bitnami Helm charts | Battle-tested, maintained weekly |
| API Gateway | Keep Kong (existing config) | Preserves rate limiting, CORS, security headers |
| Secrets | K8s Secrets (hybrid pattern) | Shared config + per-service isolation |
| Monitoring | Prometheus + Grafana | Industry standard observability |
| CI/CD | GitHub Actions + DockerHub | Industry default registry, most universal |

---

## 1. Directory Structure

```
k8s/
├── base/                              # Kustomize base (environment-agnostic)
│   ├── kustomization.yaml
│   ├── namespace.yaml                 # chatbox namespace
│   ├── auth-service/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml             # Service-specific: DATABASE_URL
│   │   └── serviceaccount.yaml
│   ├── chat-service/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml             # Service-specific: DATABASE_URL, AUTH/MSG URLs
│   │   └── serviceaccount.yaml
│   ├── message-service/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml             # Service-specific: DATABASE_URL, AUTH URL
│   │   └── serviceaccount.yaml
│   ├── file-service/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml             # Service-specific: DATABASE_URL, upload config
│   │   ├── pvc.yaml                   # PersistentVolumeClaim for uploads
│   │   └── serviceaccount.yaml
│   ├── frontend/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── serviceaccount.yaml
│   ├── kong/
│   │   ├── kustomization.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml             # Declarative kong.yml with K8s DNS names
│   │   └── serviceaccount.yaml
│   ├── shared-config/
│   │   ├── kustomization.yaml
│   │   ├── configmap.yaml             # chatbox-shared-config
│   │   └── secrets.yaml               # chatbox-infra-secrets (template)
│   └── secrets.env.example            # Developer reference for required secret values
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml         # Low resources, 1 replica, NodePort
│   │   └── patches/
│   │       ├── kong-service-nodeport.yaml
│   │       └── frontend-service-nodeport.yaml
│   ├── staging/
│   │   └── kustomization.yaml
│   └── prod/
│       ├── kustomization.yaml
│       └── patches/
│           ├── replicas.yaml          # 2-3 replicas per service
│           ├── resources.yaml         # Production resource limits
│           ├── hpa.yaml               # HorizontalPodAutoscaler for chat-service
│           ├── pdb.yaml               # PodDisruptionBudget
│           └── kong-service-lb.yaml   # LoadBalancer type
├── infra/
│   ├── namespace.yaml                 # chatbox-infra namespace
│   └── helm-values/
│       ├── postgres.yaml              # Bitnami PostgreSQL overrides
│       ├── redis.yaml                 # Bitnami Redis overrides
│       ├── kafka.yaml                 # Bitnami Kafka overrides (KRaft)
│       └── monitoring.yaml            # kube-prometheus-stack overrides
├── jobs/
│   ├── db-init-job.yaml               # Create databases + schemas
│   └── kafka-init-job.yaml            # Create Kafka topics
├── scripts/
│   ├── setup-local.sh                 # One-command local setup (kind + infra + apps)
│   ├── deploy.sh                      # Deploy/update app services
│   ├── teardown.sh                    # Clean everything
│   ├── build-images.sh               # Build all Docker images
│   └── generate-secrets.sh            # Generate K8s Secret YAML from env vars
└── Makefile                           # (at repo root, K8s targets)
```

---

## 2. Namespace Strategy

| Namespace | Contains | Purpose |
|-----------|----------|---------|
| `chatbox` | auth, chat, message, file, frontend, kong | Application services |
| `chatbox-infra` | PostgreSQL, Redis, Kafka | Infrastructure (different lifecycle) |
| `chatbox-monitoring` | Prometheus, Grafana | Observability stack |

---

## 3. Infrastructure Layer (Helm Charts)

### PostgreSQL (Bitnami)
- **Chart:** `oci://registry-1.docker.io/bitnamicharts/postgresql` — pin to latest stable at time of implementation
- **Single instance**, 4 databases created by init job
- **Helm values:** `max_connections: 200`, persistence 8Gi (dev) / 50Gi (prod)
- **Auth:** `chatbox-postgres-secret` K8s Secret

### Redis (Bitnami)
- **Chart:** `oci://registry-1.docker.io/bitnamicharts/redis` — pin to latest stable
- **Standalone mode** (no sentinel for dev)
- **Auth:** Password from K8s Secret
- **Persistence:** 2Gi (dev)

### Kafka (Bitnami)
- **Chart:** `oci://registry-1.docker.io/bitnamicharts/kafka` — pin to latest stable
- **KRaft mode** (no ZooKeeper)
- **Single broker** (dev), 3 (prod)
- **Persistence:** 8Gi (dev)

**Version pinning:** All Helm chart versions are pinned in `scripts/setup-local.sh` using `--version X.Y.Z`. Run `helm search repo bitnami/<chart>` to find latest stable versions at implementation time.

### Init Jobs

**db-init-job:**
- K8s Job using `postgres:16-alpine`
- initContainer waits for Postgres readiness (`nc -z`)
- Creates 4 databases: `chatbox_auth`, `chatbox_chat`, `chatbox_messages`, `chatbox_files`
- Applies table schemas (from existing `infra/docker/init/init-db.sh` logic)
- `restartPolicy: OnFailure`, `backoffLimit: 5`

**kafka-init-job:**
- K8s Job using `bitnami/kafka` image
- initContainer waits for Kafka readiness
- Creates 6 topics with partition counts:
  - `chat.messages` (6), `chat.private` (3), `chat.events` (3)
  - `chat.dlq` (1), `file.events` (3), `auth.events` (3)

---

## 4. Application Services (Kustomize Base)

### Common Patterns (all services):

**Health Checks:**
```yaml
livenessProbe:
  httpGet: { path: /health, port: <port> }
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3
readinessProbe:
  httpGet: { path: /health, port: <port> }
  initialDelaySeconds: 5
  periodSeconds: 10
```

**SecurityContext:**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true  # where possible
```

**Resource Defaults (base):**
```yaml
resources:
  requests: { cpu: 50m, memory: 64Mi }
  limits: { cpu: 250m, memory: 256Mi }
```

**Labels:**
```yaml
labels:
  app.kubernetes.io/name: <service-name>
  app.kubernetes.io/part-of: chatbox
  app.kubernetes.io/component: <backend|frontend|gateway>
```

**ServiceAccount:** One per service for fine-grained RBAC.

### Per-Service Details:

#### auth-service
- **Port:** 8001
- **Replicas:** 1 (dev) / 2 (prod)
- **initContainers:**
  1. `wait-for-postgres` — `nc -z postgres-postgresql.chatbox-infra 5432`
  2. `wait-for-redis` — `nc -z redis-master.chatbox-infra 6379`
  3. `wait-for-kafka` — `nc -z kafka.chatbox-infra 9092`
  4. `run-migrations` — `alembic upgrade head`
- **Env from:** `chatbox-shared-config`, `chatbox-infra-secrets`, `auth-service-config`, `auth-admin-secret`

#### chat-service
- **Port:** 8003
- **Replicas:** 1 (dev) / 3 (prod) + HPA
- **terminationGracePeriodSeconds:** 30 (WebSocket drain)
- **initContainers:**
  1. `wait-for-postgres`
  2. `wait-for-redis`
  3. `wait-for-kafka`
  4. `wait-for-auth` — `nc -z auth-service.chatbox 8001`
- **Env from:** `chatbox-shared-config`, `chatbox-infra-secrets`, `chat-service-config`
- **Note:** Redis pub/sub handles WebSocket scaling — no sticky sessions needed.

#### message-service
- **Port:** 8004
- **Replicas:** 1 (dev) / 2 (prod)
- **initContainers:**
  1. `wait-for-postgres`
  2. `wait-for-kafka`
  3. `run-migrations` — `alembic upgrade head`
- **Env from:** `chatbox-shared-config`, `chatbox-infra-secrets`, `message-service-config`
- **Note:** Kafka consumer group handles partition assignment across replicas automatically.

#### file-service
- **Port:** 8005
- **Replicas:** 1 (dev) / 1-2 (prod, limited by PVC)
- **PVC:** `file-uploads-pvc`, 5Gi (dev) / 50Gi (prod)
  - `accessModes: [ReadWriteOnce]` — limits scaling to 1 writer
  - Prod recommendation: switch to S3/object storage for multi-replica
- **initContainers:**
  1. `wait-for-postgres`
  2. `wait-for-kafka`
  3. `run-migrations` — `npx prisma migrate deploy`
- **Env from:** `chatbox-shared-config`, `chatbox-infra-secrets`, `file-service-config`

#### frontend
- **Port:** 80 (nginx)
- **Replicas:** 1 (dev) / 2 (prod)
- **Runtime config pattern:** Entrypoint script generates `/usr/share/nginx/html/config.js` from env vars at container startup. React app loads this at runtime instead of compile-time `VITE_*` vars.
- **Env vars:** `VITE_API_BASE`, `VITE_WS_BASE` (used by entrypoint, not Vite)

#### kong
- **Port:** 8000
- **Replicas:** 1 (dev) / 2 (prod)
- **Service type:** NodePort:30080 (dev) / LoadBalancer (prod)
- **ConfigMap:** Adapted from existing `infra/kong/kong.yml` with K8s DNS names
  - All app services are in same namespace, so hostnames like `auth-service:8001` remain unchanged
- **Rate limiting:** In-memory (dev), Redis backend (prod) via overlay patch

---

## 5. Config & Secrets (Hybrid Pattern)

### Shared Resources:

**chatbox-shared-config (ConfigMap):**
Non-secret shared values only. K8s ConfigMaps cannot interpolate Secret values.
```
APP_ENV=dev
CORS_ORIGINS=http://localhost:30000,http://localhost:3000
KAFKA_BOOTSTRAP_SERVERS=kafka.chatbox-infra:9092
AUTH_SERVICE_URL=http://auth-service:8001
MESSAGE_SERVICE_URL=http://message-service:8004
```

**chatbox-infra-secrets (Secret):**
Contains full connection URLs (because they embed passwords). Generated by `scripts/generate-secrets.sh`.
```
POSTGRES_PASSWORD=<required>
REDIS_PASSWORD=<required>
SECRET_KEY=<required>
REDIS_URL=redis://:PASSWORD@redis-master.chatbox-infra:6379/0
```

### Per-Service Secrets:
URLs containing credentials go in Secrets, not ConfigMaps.

| Secret | Contents | Used by |
|--------|----------|---------|
| `auth-service-secrets` | `DATABASE_URL=postgresql://chatbox:PASS@postgres-postgresql.chatbox-infra:5432/chatbox_auth` | auth-service |
| `chat-service-secrets` | `DATABASE_URL=postgresql://chatbox:PASS@postgres-postgresql.chatbox-infra:5432/chatbox_chat` | chat-service |
| `message-service-secrets` | `DATABASE_URL=postgresql://chatbox:PASS@postgres-postgresql.chatbox-infra:5432/chatbox_messages` | message-service |
| `file-service-secrets` | `DATABASE_URL=postgresql://chatbox:PASS@postgres-postgresql.chatbox-infra:5432/chatbox_files` | file-service |
| `auth-admin-secret` | `ADMIN_USERNAME`, `ADMIN_PASSWORD` | auth-service only |

### Per-Service ConfigMaps:
Non-secret, service-specific values only.

| ConfigMap | Contents |
|-----------|----------|
| `chat-service-config` | `AUTH_SERVICE_URL`, `MESSAGE_SERVICE_URL` (can also get from shared) |
| `file-service-config` | `UPLOAD_DIR=./uploads`, `MAX_FILE_SIZE_BYTES=157286400`, `PORT=8005` |

### Developer Onboarding:
`k8s/base/secrets.env.example` with all required values and placeholder descriptions.
`scripts/generate-secrets.sh` reads a `.env` file and generates K8s Secret YAML.

---

## 6. Networking

### Traffic Flow:
```
Browser → Kong (NodePort:30080 dev / LB prod)
  ├─► auth-service:8001     (ClusterIP)
  ├─► chat-service:8003     (ClusterIP, WebSocket)
  ├─► message-service:8004  (ClusterIP)
  └─► file-service:8005     (ClusterIP)

Browser → Frontend (NodePort:30000 dev / Ingress prod)
```

### Service DNS:
- Same namespace: `auth-service:8001`
- Cross namespace: `postgres-postgresql.chatbox-infra.svc.cluster.local:5432`

---

## 7. Environment Overlays

### Dev (minikube/kind):
- 1 replica per service
- Low resources: requests 50m/64Mi, limits 250m/256Mi
- Kong: NodePort:30080
- Frontend: NodePort:30000
- Grafana: NodePort:30030
- `imagePullPolicy: IfNotPresent`
- Dev secrets with non-sensitive defaults

### Staging:
- 2 replicas per service
- Medium resources
- Same architecture as prod, lower scale

### Prod:
- 2-3 replicas per service (except file-service: 1 replica due to ReadWriteOnce PVC; chat-service: 3 + HPA)
- Production resources: requests 200m/256Mi, limits 500m/512Mi
- Kong: LoadBalancer
- HorizontalPodAutoscaler on chat-service (CPU target 70%)
- PodDisruptionBudget (minAvailable: 1) on all services
- PVC reclaim policy: Retain
- Kong rate limiting: Redis backend
- `imagePullPolicy: Always`
- Image tags: git SHA or semver

---

## 8. Monitoring & Observability

### Stack (Helm):
- **kube-prometheus-stack** (includes Prometheus + Grafana + Node Exporter + kube-state-metrics)
- Deployed to `chatbox-monitoring` namespace
- Grafana NodePort:30030 (dev)

### What's monitored (out of the box):
- Node CPU/memory/disk
- Pod health, restart counts, resource usage
- Container logs via `kubectl logs`
- K8s control plane metrics

### Grafana dashboards (pre-loaded):
- Kubernetes Cluster Overview
- Pod Resource Usage
- Node Health

### Future enhancement (not in scope):
- App-level metrics endpoints (/metrics)
- Distributed tracing
- Custom business dashboards

---

## 9. CI/CD Pipeline

### Image Registry: DockerHub (configurable)
Registry is a variable — swap to ECR/GCR/GHCR when you choose a cloud provider.
```
docker.io/<dockerhub-user>/chatbox-auth-service:<sha>
docker.io/<dockerhub-user>/chatbox-chat-service:<sha>
docker.io/<dockerhub-user>/chatbox-message-service:<sha>
docker.io/<dockerhub-user>/chatbox-file-service:<sha>
docker.io/<dockerhub-user>/chatbox-frontend:<sha>
```

### Workflow 1: `build-k8s-images.yml`
**Trigger:** Push to main or tag
**Steps:**
1. Checkout code
2. Log in to DockerHub (credentials stored as GitHub Secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`)
3. Build Docker images for all 5 services
4. Push with `:sha` and `:latest` tags

### Workflow 2: `deploy-k8s.yml`
**Trigger:** `workflow_dispatch` (manual) with environment input
**Steps:**
1. Configure kubectl with cluster credentials (GitHub Secrets)
2. Update Kustomize overlay image tags via `kustomize edit set image`
3. `kubectl apply -k overlays/<environment>`
4. Wait for rollout completion
5. Smoke test health endpoints

---

## 10. Developer Experience (Makefile)

```makefile
# Cluster lifecycle
k8s-setup-local         # Full setup: kind cluster + infra + init jobs + build + deploy
k8s-teardown            # Full teardown: remove everything, delete kind cluster

# Infrastructure
k8s-infra-setup         # Install Postgres, Redis, Kafka via Helm
k8s-infra-teardown      # Remove Helm infra releases only
k8s-init-jobs           # Run db-init and kafka-init jobs

# Application
k8s-build               # Build all Docker images, load into kind
k8s-deploy              # Deploy/update all app services (kubectl apply -k)
k8s-redeploy SVC=name   # Rebuild + reload + restart one service
k8s-validate            # Dry-run kustomize, validate YAML before applying

# Operations
k8s-status              # Show pods, services, endpoints, recent events
k8s-logs SVC=name       # Tail logs for a service
k8s-shell SVC=name      # Exec into a pod
k8s-restart SVC=name    # Rolling restart a service
k8s-port-forward        # Port-forward Kong (30080) + Frontend (30000)

# Monitoring
k8s-monitoring-setup    # Install Prometheus + Grafana via Helm
k8s-grafana             # Print Grafana URL (NodePort 30030)

# Config
k8s-secrets             # Generate K8s Secret YAML from .env file
```

---

## 11. Documentation (Two Files)

### `docs/k8s-readme.md` — Understanding (What & Why)
Explains concepts and architecture. Written for someone who has never used K8s.

1. **Overview** — What this does, high-level architecture diagram (text-based)
2. **How It Maps to Docker Compose** — Side-by-side comparison of concepts
3. **Prerequisites Explained** — What each tool is and why you need it
4. **Architecture Deep Dive** — Namespaces, services, networking, how traffic flows
5. **How Kustomize Overlays Work** — Base + patches = environment-specific config
6. **How the CI/CD Pipeline Works** — Image build, registry push, deployment flow
7. **Production Considerations** — Managed services, TLS, backups, connection pooling, S3
8. **K8s Concepts Glossary** — Pod, Deployment, Service, ConfigMap, Secret, PVC, Job, etc.

### `docs/k8s-operations.md` — Doing (How & Commands)
Step-by-step commands with explanations. Every command annotated.

1. **Quick Start** — `make k8s-setup-local` (one command, zero to running)
2. **Step-by-Step Setup** — Each step explained for learning
3. **Exploring the Cluster** — kubectl commands to inspect pods, services, logs, events
4. **Common Operations** — Redeploy, scale, update config, restart, view logs
5. **Monitoring** — Access Grafana, read dashboards, check resource usage
6. **Troubleshooting** — CrashLoopBackOff, Pending, connection errors, init job failures, image issues, OOM, PVC
7. **Teardown** — Clean removal of everything
8. **Reference** — All Makefile targets, services & ports table, env vars, Helm chart versions

---

## 12. Implementation Plan

### Phase 0: Branch Setup
0. Create branch `feature/k8s-support` from main

### Phase 1: Foundation (Infrastructure)
1. Create `k8s/` directory structure
2. Create namespace manifests (`chatbox`, `chatbox-infra`, `chatbox-monitoring`)
3. Write Bitnami Helm values for PostgreSQL, Redis, Kafka
4. Write init jobs (db-init, kafka-init) — adapt from existing `infra/docker/init/` scripts
5. Write `scripts/setup-local.sh` and `scripts/teardown.sh`

### Phase 2: Application Manifests (Kustomize Base)
6. Write shared ConfigMap and Secrets template
7. Write `secrets.env.example` and `scripts/generate-secrets.sh`
8. Write Deployments + Services for all 6 components:
   - auth-service (with Alembic migration init container)
   - chat-service (with graceful shutdown, dependency waits)
   - message-service (with Alembic migration init container)
   - file-service (with Prisma migration init container, PVC)
   - frontend (with runtime config.js entrypoint)
   - kong (with ConfigMap from existing kong.yml)
9. Write ServiceAccounts for each service

### Phase 3: Environment Overlays
10. Dev overlay: NodePort, low resources, 1 replica
11. Staging overlay: medium resources, 2 replicas
12. Prod overlay: LoadBalancer, HPA, PDB, production resources

### Phase 4: Developer Experience
13. Write Makefile with all K8s targets
14. Write `scripts/build-images.sh` and `scripts/deploy.sh`

### Phase 5: Frontend Runtime Config
15. Create entrypoint script for frontend that generates config.js from env vars
16. Update frontend Dockerfile to use entrypoint

### Phase 6: Monitoring
17. Write Helm values for kube-prometheus-stack
18. Add monitoring setup to scripts and Makefile

### Phase 7: CI/CD
19. Write `build-k8s-images.yml` GitHub Actions workflow
20. Write `deploy-k8s.yml` GitHub Actions workflow

### Phase 8: Documentation
21. Write `docs/k8s-readme.md` — Understanding guide (architecture, concepts, why)
22. Write `docs/k8s-operations.md` — Operations guide (commands, troubleshooting, how)

### Phase 9: Verification
23. Test full local setup: `make k8s-setup-local`
24. Verify all pods running and healthy
25. Test app end-to-end (register, login, create room, send message, upload file)
26. Verify monitoring (Grafana accessible, dashboards working)
27. Test teardown: `make k8s-teardown`

---

## Critical Files to Modify/Create

### Existing files to reference (reuse logic):
- `infra/docker/init/init-db.sh` — Database initialization SQL
- `infra/docker/init/init-kafka.sh` — Kafka topic creation
- `infra/kong/kong.yml` — Kong declarative configuration
- `docker-compose.yml` — Current service definitions, env vars, ports
- `services/*/Dockerfile` — Existing Docker builds
- `.github/workflows/` — Existing CI pipelines

### New files to create:
- All files under `k8s/` directory (see structure above)
- `Makefile` (K8s targets, at repo root — add to existing if present)
- `docs/k8s-readme.md` — Understanding guide (what & why)
- `docs/k8s-operations.md` — Operations guide (how & commands)
- `.github/workflows/build-k8s-images.yml`
- `.github/workflows/deploy-k8s.yml`
- `services/frontend/docker-entrypoint.sh` — Runtime config.js generation

---

## Verification Plan

1. **Local cluster:** `make k8s-setup-local` creates kind cluster, installs infra, deploys apps
2. **Pod health:** All pods in `Running` state, no `CrashLoopBackOff`
3. **Init jobs:** db-init and kafka-init Jobs completed successfully
4. **Service connectivity:** `kubectl exec` into auth-service, `curl http://chat-service:8003/health`
5. **End-to-end:** Access frontend at `http://localhost:30000`, register user, login, create room, send message
6. **Monitoring:** Access Grafana at `http://localhost:30030`, see cluster dashboard
7. **Teardown:** `make k8s-teardown` removes all resources cleanly
