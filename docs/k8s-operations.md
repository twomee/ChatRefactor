# Kubernetes Operations Guide — Running Chatbox on K8s

This guide contains **commands and step-by-step instructions** for running, managing, and troubleshooting Chatbox on Kubernetes. For understanding the architecture and concepts, see [k8s-readme.md](./k8s-readme.md).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Step-by-Step Setup](#step-by-step-setup)
3. [Exploring the Cluster](#exploring-the-cluster)
4. [Common Operations](#common-operations)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)
7. [Teardown](#teardown)
8. [Reference](#reference)

---

## Quick Start

**One command to go from zero to running:**

```bash
make k8s-setup-local
```

This single command will:
1. Create a local Kubernetes cluster using `kind`
2. Install PostgreSQL and Redis via Helm, Kafka via plain manifest
3. Create databases and Kafka topics
4. Build all Docker images
5. Deploy all application services

When it's done:
- **Frontend:** http://localhost:30000
- **API (Kong):** http://localhost:30080

### Prerequisites

Install these tools first:

**Ubuntu/Debian:**
```bash
# Docker
sudo apt-get update && sudo apt-get install -y docker.io
sudo usermod -aG docker $USER  # Log out and back in after this

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64
sudo install -o root -g root -m 0755 kind /usr/local/bin/kind

# Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

**macOS:**
```bash
brew install docker kubectl kind helm
```

Verify everything is installed:
```bash
docker --version    # Docker version 24+
kubectl version --client    # Client Version: v1.28+
kind --version      # kind v0.24+
helm version        # v3.13+
```

---

## Step-by-Step Setup

If you want to understand each step instead of using the one-command setup.

### Step 1: Create the Cluster

```bash
# Create a kind cluster named "chatbox" with port mappings
kind create cluster --name chatbox --config - <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 30080      # Kong API Gateway
        protocol: TCP
      - containerPort: 30000
        hostPort: 30000      # Frontend
        protocol: TCP
      - containerPort: 30030
        hostPort: 30030      # Grafana (monitoring)
        protocol: TCP
EOF
```

What this does:
- Creates a single-node K8s cluster running inside a Docker container
- Maps ports from the cluster to your machine so you can access services

Verify:
```bash
kubectl cluster-info
# Should show: Kubernetes control plane is running at https://127.0.0.1:PORT
```

### Step 2: Create Namespaces

```bash
kubectl apply -f k8s/base/namespace.yaml       # chatbox namespace
kubectl apply -f k8s/infra/namespace.yaml       # chatbox-infra + chatbox-monitoring
```

Verify:
```bash
kubectl get namespaces
# Should show: chatbox, chatbox-infra, chatbox-monitoring
```

### Step 3: Install Infrastructure

```bash
# Add the Bitnami Helm repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Load passwords from your secrets file (never hardcode them here)
source k8s/secrets.env   # or k8s/base/secrets.env.example for defaults

# Install PostgreSQL
helm upgrade --install postgres bitnami/postgresql \
  --namespace chatbox-infra \
  --values k8s/infra/helm-values/postgres.yaml \
  --version 18.5.14 \
  --set auth.postgresPassword="$POSTGRES_PASSWORD" \
  --set auth.password="$POSTGRES_PASSWORD" \
  --wait --timeout 180s

# Install Redis
helm upgrade --install redis bitnami/redis \
  --namespace chatbox-infra \
  --values k8s/infra/helm-values/redis.yaml \
  --version 25.3.9 \
  --set auth.password="$REDIS_PASSWORD" \
  --wait --timeout 120s

# Install Kafka — plain manifest, NOT a Helm chart
kubectl apply -f k8s/infra/kafka.yaml
kubectl rollout status deployment/kafka --namespace chatbox-infra --timeout=120s
```

Verify:
```bash
kubectl get pods -n chatbox-infra
# All pods should be Running and Ready (1/1)
```

### Step 4: Apply Secrets

```bash
bash k8s/scripts/generate-secrets.sh
```

This creates K8s Secret objects from your environment variables. If you haven't created a `k8s/secrets.env` file, it uses the defaults from `k8s/base/secrets.env.example`.

### Step 5: Run Init Jobs

```bash
# Delete any previous runs first (jobs are not re-runnable by default)
kubectl delete job db-init kafka-init --namespace chatbox --ignore-not-found

# Apply init jobs (create 4 databases + tables, create Kafka topics)
kubectl apply -f k8s/jobs/db-init-job.yaml
kubectl apply -f k8s/jobs/kafka-init-job.yaml

# Wait for completion
kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s
```

Verify:
```bash
kubectl get jobs -n chatbox
# Both jobs should show COMPLETIONS: 1/1
```

### Step 6: Build Docker Images

```bash
# Option A: script (builds all 5 and loads into kind)
bash k8s/scripts/build-images.sh

# Option B: manually, one service at a time
docker build -t auth-service:latest services/auth-service/
docker build -t chat-service:latest services/chat-service/
docker build -t message-service:latest services/message-service/
docker build -t file-service:latest services/file-service/
docker build -t frontend:latest \
  --build-arg VITE_API_BASE=http://localhost:30080 \
  --build-arg VITE_WS_BASE=ws://localhost:30080 \
  frontend/

# Load each image into the kind cluster
kind load docker-image auth-service:latest --name chatbox
kind load docker-image chat-service:latest --name chatbox
kind load docker-image message-service:latest --name chatbox
kind load docker-image file-service:latest --name chatbox
kind load docker-image frontend:latest --name chatbox
```

Verify:
```bash
docker exec chatbox-control-plane crictl images | grep -E "auth|chat|message|file|frontend"
```

### Step 7: Deploy Application

```bash
kubectl apply -k k8s/overlays/dev

# Re-apply secrets immediately after — the base manifests contain CHANGE_ME
# placeholders that kustomize will have just overwritten your real secrets with
bash k8s/scripts/generate-secrets.sh
```

Verify:
```bash
kubectl get pods -n chatbox
# Wait for all pods to show Running and Ready (1/1)
# Init containers run first — this may take 1-2 minutes
```

### Step 8: Access the App

- **Frontend:** http://localhost:30000
- **API:** http://localhost:30080
- **Test the API:** `curl http://localhost:30080/auth/ping`

---

## Exploring the Cluster

### View All Pods

```bash
# Application pods
kubectl get pods -n chatbox

# Infrastructure pods
kubectl get pods -n chatbox-infra

# All namespaces at once
kubectl get pods -A | grep chatbox
```

Output explained:
```
NAME                              READY   STATUS    RESTARTS   AGE
auth-service-7d8f9b6c4d-x2k9p    1/1     Running   0          5m
│                                  │       │         │
│                                  │       │         └── Times the container was restarted
│                                  │       └── Current state (Running = healthy)
│                                  └── Ready containers / Total containers
└── Pod name (deployment name + random suffix)
```

### View Services

```bash
kubectl get svc -n chatbox
```

Output explained:
```
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)
kong              NodePort    10.96.45.12     <none>        80:30080/TCP
│                 │                                         │
│                 │                                         └── External port : Internal port
│                 └── How the service is exposed
└── Service name (used as DNS hostname)
```

### View Logs

```bash
# Follow logs for a specific service (all pods)
kubectl logs -f -l app.kubernetes.io/name=auth-service -n chatbox

# View logs for a specific pod
kubectl logs auth-service-7d8f9b6c4d-x2k9p -n chatbox

# View init container logs (useful for debugging startup)
kubectl logs auth-service-7d8f9b6c4d-x2k9p -n chatbox -c wait-for-postgres
kubectl logs auth-service-7d8f9b6c4d-x2k9p -n chatbox -c run-migrations

# View last 50 lines
kubectl logs -l app.kubernetes.io/name=chat-service -n chatbox --tail=50
```

### Exec Into a Container

```bash
# Open a shell inside a running container
kubectl exec -it deployment/auth-service -n chatbox -- /bin/sh

# Run a single command
kubectl exec deployment/auth-service -n chatbox -- env | grep DATABASE

# Test connectivity from inside a pod
kubectl exec deployment/auth-service -n chatbox -- \
  wget -q -O- http://chat-service:8003/health
```

### View Events

```bash
# Recent events (shows scheduling, pulling, starting, errors)
kubectl get events -n chatbox --sort-by='.lastTimestamp' | tail -20

# Events for a specific pod
kubectl describe pod auth-service-7d8f9b6c4d-x2k9p -n chatbox
# Scroll to the "Events" section at the bottom
```

### View Resource Usage

```bash
# Pod CPU and memory usage (requires metrics-server)
kubectl top pods -n chatbox

# Node resource usage
kubectl top nodes
```

---

## Common Operations

### Redeploy a Service After Code Changes

```bash
# Option A: One command (rebuild + reload + restart)
make k8s-redeploy SVC=auth-service

# Option B: Manual steps
docker build -t auth-service:latest services/auth-service/
kind load docker-image auth-service:latest --name chatbox
kubectl rollout restart deployment/auth-service -n chatbox
```

### Scale a Service

```bash
# Scale to 3 replicas
kubectl scale deployment/chat-service --replicas=3 -n chatbox

# Verify
kubectl get pods -n chatbox -l app.kubernetes.io/name=chat-service
# Should show 3 pods
```

### Rolling Restart (No Downtime)

```bash
# Restart all pods of a service one by one
kubectl rollout restart deployment/auth-service -n chatbox

# Watch the rollout progress
kubectl rollout status deployment/auth-service -n chatbox
```

### Update Configuration

```bash
# Edit a ConfigMap
kubectl edit configmap chatbox-shared-config -n chatbox

# IMPORTANT: Pods don't automatically pick up ConfigMap changes!
# You must restart the affected services:
kubectl rollout restart deployment/auth-service -n chatbox
kubectl rollout restart deployment/chat-service -n chatbox
```

### Update Secrets

```bash
# Edit your secrets.env file, then regenerate:
bash k8s/scripts/generate-secrets.sh

# Restart affected services to pick up new values:
kubectl rollout restart deployment/auth-service -n chatbox
```

### View Deployment History

```bash
# See rollout history
kubectl rollout history deployment/auth-service -n chatbox

# Rollback to previous version
kubectl rollout undo deployment/auth-service -n chatbox
```

---

## Monitoring

### Install Monitoring Stack

```bash
make k8s-monitoring-setup
```

This installs Prometheus (metrics collection) and Grafana (dashboards).

### Access Grafana

```
URL: http://localhost:30030
Username: admin
Password: admin
```

### Pre-loaded Dashboards

After logging into Grafana:
1. Click the **hamburger menu** (top left) > **Dashboards**
2. Look for these dashboards:
   - **Kubernetes / Compute Resources / Namespace (Pods)** — CPU and memory per pod
   - **Kubernetes / Compute Resources / Cluster** — Cluster-wide resource usage
   - **Node Exporter / Nodes** — Host machine metrics

### Quick Health Check (No Grafana)

```bash
# Check all pods are running
make k8s-status

# Check resource usage
kubectl top pods -n chatbox

# Check for recent errors
kubectl get events -n chatbox --field-selector type=Warning
```

---

## Troubleshooting

### Pod Stuck in `CrashLoopBackOff`

**What it means:** The container starts, crashes, K8s restarts it, it crashes again.

**How to diagnose:**
```bash
# Check the pod's logs
kubectl logs <pod-name> -n chatbox

# If the pod is restarting too fast to read logs:
kubectl logs <pod-name> -n chatbox --previous

# Check init container logs (might be failing before the main container)
kubectl describe pod <pod-name> -n chatbox
# Look at the "Init Containers" section and "Events" section
```

**Common causes:**
- Database not ready (init container timeout) — check if infra pods are running
- Wrong environment variable (DATABASE_URL typo, wrong password)
- Application bug (check the logs)
- Out of memory (check resource limits)

### Pod Stuck in `Pending`

**What it means:** K8s can't schedule the pod on any node.

**How to diagnose:**
```bash
kubectl describe pod <pod-name> -n chatbox
# Look at "Events" section — it usually says why
```

**Common causes:**
- Not enough CPU or memory on the node. Fix: lower resource requests or add nodes
- PVC can't be provisioned. Fix: check storage class exists
- Image pull error. Fix: check image name and ensure it's loaded into kind

### Pod Stuck in `Init:0/3` or Similar

**What it means:** Init containers are running (or failing).

```bash
# Check which init container is stuck
kubectl describe pod <pod-name> -n chatbox

# Check logs of the stuck init container
kubectl logs <pod-name> -n chatbox -c wait-for-postgres
```

**Common causes:**
- Infrastructure not ready. Fix: check `kubectl get pods -n chatbox-infra`
- Wrong hostname. Fix: verify DNS names in the init container commands

### Services Can't Connect to Each Other

```bash
# Verify the target service exists
kubectl get svc -n chatbox

# Test DNS resolution from inside a pod
kubectl exec deployment/auth-service -n chatbox -- nslookup chat-service

# Test HTTP connectivity
kubectl exec deployment/auth-service -n chatbox -- \
  wget -q -O- http://chat-service:8003/health
```

**Common causes:**
- Service name typo in environment variable
- Target service not running (check pods)
- Wrong port number

### Init Jobs Failed

```bash
# Check job status
kubectl get jobs -n chatbox

# View job logs
kubectl logs job/db-init -n chatbox
kubectl logs job/kafka-init -n chatbox

# Delete and re-run
kubectl delete job db-init kafka-init -n chatbox --ignore-not-found
kubectl apply -f k8s/jobs/db-init-job.yaml
kubectl apply -f k8s/jobs/kafka-init-job.yaml
```

### Images Not Found

```bash
# If you see: ErrImagePull or ImagePullBackOff
kubectl describe pod <pod-name> -n chatbox
# Look for the image pull error message

# Verify images are loaded into kind
docker exec chatbox-control-plane crictl images | grep auth-service

# Reload images
kind load docker-image auth-service:latest --name chatbox
```

### Out of Memory (OOMKilled)

```bash
# Check if any containers were killed for using too much memory
kubectl get pods -n chatbox
# Look for RESTARTS column — OOMKilled pods restart frequently

# Check the reason
kubectl describe pod <pod-name> -n chatbox
# Look for "Last State: Terminated, Reason: OOMKilled"

# Fix: increase memory limits in the overlay
# Edit k8s/overlays/dev/kustomization.yaml to add resource patches
```

### PVC Problems

```bash
# Check PVC status
kubectl get pvc -n chatbox
# STATUS should be "Bound"

# If stuck in "Pending":
kubectl describe pvc <pvc-name> -n chatbox
# Usually means no StorageClass is available

# For kind, the default StorageClass should work
kubectl get storageclass
```

### Reset Everything

If everything is broken and you want to start fresh:
```bash
make k8s-teardown    # Delete cluster
make k8s-setup-local # Recreate from scratch
```

---

## Teardown

### Remove Everything

```bash
make k8s-teardown
```

This will:
1. Delete all application resources (dev overlay)
2. Delete init jobs
3. Uninstall Helm releases (Postgres, Redis), remove Kafka manifest
4. Uninstall monitoring (Prometheus + Grafana)
5. Delete the kind cluster

### Remove Only App (Keep Infrastructure)

```bash
kubectl delete -k k8s/overlays/dev
```

### Remove Only Monitoring

```bash
helm uninstall monitoring --namespace chatbox-monitoring
```

---

## Reference

### All Makefile Targets

| Target | Description | Example |
|--------|-------------|---------|
| `k8s-setup-local` | Full local setup (one command) | `make k8s-setup-local` |
| `k8s-teardown` | Full teardown | `make k8s-teardown` |
| `k8s-infra-setup` | Install infra only (Helm) | `make k8s-infra-setup` |
| `k8s-infra-teardown` | Remove infra only | `make k8s-infra-teardown` |
| `k8s-init-jobs` | Run init jobs (db + kafka) | `make k8s-init-jobs` |
| `k8s-build` | Build all Docker images | `make k8s-build` |
| `k8s-deploy` | Deploy app services | `make k8s-deploy` |
| `k8s-redeploy` | Rebuild + restart one service | `make k8s-redeploy SVC=auth-service` |
| `k8s-validate` | Validate YAML (dry run) | `make k8s-validate` |
| `k8s-status` | Show cluster status | `make k8s-status` |
| `k8s-logs` | Tail service logs | `make k8s-logs SVC=chat-service` |
| `k8s-shell` | Exec into a pod | `make k8s-shell SVC=auth-service` |
| `k8s-restart` | Rolling restart | `make k8s-restart SVC=auth-service` |
| `k8s-port-forward` | Show access URLs | `make k8s-port-forward` |
| `k8s-monitoring-setup` | Install Prometheus + Grafana | `make k8s-monitoring-setup` |
| `k8s-grafana` | Show Grafana URL and credentials | `make k8s-grafana` |
| `k8s-prometheus` | Port-forward Prometheus → localhost:9090 | `make k8s-prometheus` |
| `k8s-secrets` | Generate K8s secrets | `make k8s-secrets` |

### Services & Ports

| Service | Internal Port | External Access (dev) | Protocol |
|---------|---------------|----------------------|----------|
| Kong (API Gateway) | 8000 | http://localhost:30080 | HTTP |
| Frontend | 80 | http://localhost:30000 | HTTP |
| Grafana | 3000 | http://localhost:30030 | HTTP |
| auth-service | 8001 | Via Kong: /auth/* | HTTP |
| chat-service | 8003 | Via Kong: /rooms/*, /ws, /pm, /admin | HTTP/WS |
| message-service | 8004 | Via Kong: /messages/* | HTTP |
| file-service | 8005 | Via Kong: /files/* | HTTP |
| PostgreSQL | 5432 | Internal only | TCP |
| Redis | 6379 | Internal only | TCP |
| Kafka | 9092 | Internal only | TCP |

### Environment Variables

**Shared (all services):**
| Variable | Source | Value |
|----------|--------|-------|
| APP_ENV | ConfigMap | dev |
| KAFKA_BOOTSTRAP_SERVERS | ConfigMap | kafka.chatbox-infra:9092 |
| AUTH_SERVICE_URL | ConfigMap | http://auth-service:8001 |
| MESSAGE_SERVICE_URL | ConfigMap | http://message-service:8004 |
| CORS_ORIGINS | ConfigMap | http://localhost:30000,http://localhost:3000 |
| POSTGRES_PASSWORD | Secret | (from secrets.env) |
| REDIS_PASSWORD | Secret | (from secrets.env) |
| SECRET_KEY | Secret | (from secrets.env) |
| REDIS_URL | Secret | redis://default:PASS@redis-master.chatbox-infra:6379/0 |

**Per-service:**
| Variable | Service | Source |
|----------|---------|--------|
| DATABASE_URL | Each service | Per-service Secret (different database per service) |
| ADMIN_USERNAME | auth-service | auth-admin-secret |
| ADMIN_PASSWORD | auth-service | auth-admin-secret |
| UPLOAD_DIR | file-service | file-service-config ConfigMap |
| MAX_FILE_SIZE_BYTES | file-service | file-service-config ConfigMap |
| PORT | chat-service, file-service | Per-service ConfigMap |

### Directory Structure

```
k8s/
├── base/                    # Default manifests (environment-agnostic)
│   ├── kustomization.yaml   # Lists all resources
│   ├── namespace.yaml       # chatbox namespace
│   ├── shared-config/       # Shared ConfigMap + Secrets
│   ├── auth-service/        # Deployment, Service, SA, Secrets
│   ├── chat-service/
│   ├── message-service/
│   ├── file-service/        # + PVC for uploads
│   ├── frontend/
│   └── kong/                # + ConfigMap with kong.yml
├── overlays/
│   ├── dev/                 # Local: NodePort, 1 replica
│   ├── staging/             # 2 replicas (requires DockerHub images)
│   ├── prod/                # LoadBalancer, HPA, PDB (requires DockerHub images)
│   ├── staging-kind/        # staging config using local kind images
│   └── prod-kind/           # prod config using local kind images
├── infra/
│   ├── namespace.yaml       # chatbox-infra + chatbox-monitoring
│   └── helm-values/         # Helm chart configuration
├── jobs/                    # DB init + Kafka topic init
└── scripts/                 # Automation scripts
```
