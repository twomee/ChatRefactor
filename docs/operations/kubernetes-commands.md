# Kubernetes Operations Guide — Running Chatbox on K8s

This guide contains **commands and step-by-step instructions** for running, managing, and troubleshooting Chatbox on Kubernetes. For understanding the architecture and concepts, see [kubernetes-guide.md](./kubernetes-guide.md).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running by Environment](#running-by-environment)
3. [Running via Makefile](#running-via-makefile)
4. [Step-by-Step Setup](#step-by-step-setup)
5. [Resource Commands Reference](#resource-commands-reference)
6. [Common Operations](#common-operations)
7. [Monitoring](#monitoring)
8. [Troubleshooting](#troubleshooting)
9. [Teardown](#teardown)
10. [Reference](#reference)

---

## Quick Start

**One command to go from zero to running:**

```bash
make k8s-setup-local
```

This single command will:
1. Create a local Kubernetes cluster using `kind`
2. Install the monitoring stack (Prometheus + Grafana) — **must run before infra** because PostgreSQL and Redis Helm charts create `ServiceMonitor` resources that require the Prometheus Operator CRDs to exist
3. Install PostgreSQL and Redis via Helm, Kafka via plain manifest
4. Create databases and Kafka topics
5. Build all Docker images
6. Deploy all application services

When it's done:
- **Frontend:** http://localhost:30000
- **API (Kong):** http://localhost:30080
- **Grafana:** http://localhost:30030 (admin / admin)

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

## Running by Environment

The same infrastructure (Postgres, Redis, Kafka) runs for all environments. What changes per environment is the **Kustomize overlay** — it controls how many replicas run, what resource limits are set, and how services are exposed.

---

### Dev — 1 replica, local kind cluster

Use this for everyday development. It's the default.

```bash
# Full setup from zero (creates cluster, installs infra, builds images, deploys)
bash infra/k8s/scripts/setup-local.sh
# or: make k8s-setup-local

# Deploy / re-deploy app only (infra already running)
bash infra/k8s/scripts/deploy.sh dev
# or: make k8s-deploy

# After changing code in one service — rebuild + restart just that service
make k8s-redeploy SVC=auth-service
# valid values: auth-service, chat-service, message-service, file-service, frontend, kong

# Manual kubectl equivalent
kubectl apply -k infra/k8s/overlays/dev
bash infra/k8s/scripts/generate-secrets.sh   # always re-run after kustomize apply
```

**Access:** Frontend → http://localhost:30000 | API → http://localhost:30080

---

### Staging-kind — 2 replicas, local kind cluster

Same config as staging (2 replicas per service) but uses your locally built images instead of DockerHub. Use this to test the staging overlay before pushing images to a registry.

```bash
# Deploy the staging overlay (images must already be loaded into kind)
bash infra/k8s/scripts/deploy.sh staging-kind
# or: make k8s-deploy OVERLAY=staging-kind

# Manual kubectl equivalent
kubectl apply -k infra/k8s/overlays/staging-kind
bash infra/k8s/scripts/generate-secrets.sh
```

**What's different vs dev:** 2 replicas for every service instead of 1.

**Access:** same ports — Frontend → http://localhost:30000 | API → http://localhost:30080

---

### Prod-kind — 3 chat replicas + HPA + PDB, local kind cluster

Full production config but using locally built images. Use this to validate the production overlay locally before deploying to a real cluster.

```bash
# Deploy the prod overlay (images must already be loaded into kind)
bash infra/k8s/scripts/deploy.sh prod-kind
# or: make k8s-deploy OVERLAY=prod-kind

# Manual kubectl equivalent
kubectl apply -k infra/k8s/overlays/prod-kind
bash infra/k8s/scripts/generate-secrets.sh
```

**What's different vs dev:**
- `chat-service` → 3 replicas (scales up to 10 automatically based on CPU)
- All other services → 2 replicas
- `HorizontalPodAutoscaler` active on chat-service (CPU target: 70%)
- `PodDisruptionBudgets` on all 5 services (K8s won't take all pods offline at once during maintenance)

**Verify the HPA is active:**
```bash
kubectl get hpa -n chatbox
# NAME                  REFERENCE                TARGETS   MINPODS   MAXPODS   REPLICAS
# chat-service-hpa      Deployment/chat-service  0%/70%    3         10        3
```

**Access:** same ports — Frontend → http://localhost:30000 | API → http://localhost:30080

---

### Staging / Prod — real cluster (requires DockerHub images)

These overlays are for deployment to a real cloud cluster (AWS EKS, GKE, AKS). They expect images to already exist in DockerHub.

```bash
# Push images to DockerHub first (done automatically by CI, or manually)
docker push <your-dockerhub-user>/chatbox-auth-service:latest
# ... repeat for all 5 services

# Then deploy
bash infra/k8s/scripts/deploy.sh staging
bash infra/k8s/scripts/deploy.sh prod
```

> **Note:** Your kubeconfig must point to the target cluster (`kubectl config current-context`).

---

## Running via Makefile

All `make` targets run from the project root. Variables are passed inline: `make <target> VAR=value`.

### Variables

| Variable | Default | What it controls |
|----------|---------|-----------------|
| `OVERLAY` | `dev` | Which Kustomize overlay to deploy (`dev`, `staging-kind`, `prod-kind`, `staging`, `prod`) |
| `SVC` | *(none)* | Which service to target (`auth-service`, `chat-service`, `message-service`, `file-service`, `frontend`, `kong`) |
| `CLUSTER_NAME` | `chatbox` | The kind cluster name |

---

### Cluster Lifecycle

```bash
make k8s-setup-local     # Zero to running: create cluster + infra + secrets + init jobs + images + deploy
make k8s-teardown        # Tear down everything and delete the kind cluster
```

---

### Infrastructure

```bash
make k8s-infra-setup     # Install PostgreSQL + Redis via Helm, Kafka via manifest (reads infra/k8s/secrets.env)
make k8s-infra-teardown  # Uninstall Helm releases and Kafka (keeps the kind cluster and app running)
make k8s-init-jobs       # Delete + re-run db-init and kafka-init jobs (creates databases and topics)
make k8s-secrets         # Read infra/k8s/secrets.env and create/update all K8s Secrets
```

---

### Application

```bash
make k8s-build                        # Build all 5 Docker images and load into kind

make k8s-deploy                       # Apply dev overlay and wait for all rollouts
make k8s-deploy OVERLAY=staging-kind  # Apply staging-kind overlay
make k8s-deploy OVERLAY=prod-kind     # Apply prod-kind overlay

make k8s-validate                     # Dry-run — validate YAML against the cluster without applying
make k8s-validate OVERLAY=prod-kind   # Validate a specific overlay

# Rebuild one service, reload into kind, and do a rolling restart
make k8s-redeploy SVC=auth-service
make k8s-redeploy SVC=chat-service
make k8s-redeploy SVC=message-service
make k8s-redeploy SVC=file-service
make k8s-redeploy SVC=frontend
```

---

### Operations

```bash
make k8s-status                      # Print pods, services, infra pods, and recent events — quick health check

make k8s-logs SVC=auth-service       # Tail live logs for all auth-service pods
make k8s-logs SVC=chat-service       # Tail live logs for all chat-service pods
make k8s-logs SVC=message-service    # Tail live logs for all message-service pods
make k8s-logs SVC=file-service       # Tail live logs for all file-service pods
make k8s-logs SVC=frontend           # Tail live logs for the frontend pod
make k8s-logs SVC=kong               # Tail live logs for the kong gateway pod

make k8s-shell SVC=auth-service      # Open /bin/sh shell inside a running auth-service pod
make k8s-shell SVC=chat-service      # Same for chat-service
make k8s-shell SVC=message-service   # Same for message-service
make k8s-shell SVC=file-service      # Same for file-service

make k8s-restart SVC=auth-service    # Rolling restart auth-service (zero downtime)
make k8s-restart SVC=chat-service
```

---

### Monitoring

```bash
make k8s-monitoring-setup            # Install Prometheus + Grafana via Helm
make k8s-monitoring-teardown         # Uninstall monitoring stack
make k8s-monitoring-access           # Print Grafana URL + admin password
```

> For non-K8s Make targets (Docker Compose), see [Makefile Reference](makefile-reference.md).

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
kubectl apply -f infra/k8s/base/namespace.yaml       # chatbox namespace
kubectl apply -f infra/k8s/infra/namespace.yaml       # chatbox-infra + chatbox-monitoring
```

Verify:
```bash
kubectl get namespaces
# Should show: chatbox, chatbox-infra, chatbox-monitoring
```

### Step 3: Install Monitoring Stack

> **Must run before infra.** The PostgreSQL and Redis Helm charts create `ServiceMonitor` resources. These are a custom resource type (CRD) defined by the Prometheus Operator. If the monitoring stack isn't installed first, Helm will fail with: `no matches for kind "ServiceMonitor" in version "monitoring.coreos.com/v1"`.

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace chatbox-monitoring \
  --values infra/k8s/infra/helm-values/monitoring.yaml \
  --version 82.14.1 \
  --wait --timeout 300s
```

Verify:
```bash
kubectl get pods -n chatbox-monitoring
# Should show: prometheus, grafana, operator, node-exporter — all Running
```

### Step 4: Install Infrastructure

```bash
# Add the Bitnami Helm repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Load passwords from your secrets file (never hardcode them here)
source infra/k8s/secrets.env   # or infra/k8s/base/secrets.env.example for defaults

# Install PostgreSQL
helm upgrade --install postgres bitnami/postgresql \
  --namespace chatbox-infra \
  --values infra/k8s/infra/helm-values/postgres.yaml \
  --version 18.5.14 \
  --set auth.postgresPassword="$POSTGRES_PASSWORD" \
  --set auth.password="$POSTGRES_PASSWORD" \
  --wait --timeout 180s

# Install Redis
helm upgrade --install redis bitnami/redis \
  --namespace chatbox-infra \
  --values infra/k8s/infra/helm-values/redis.yaml \
  --version 25.3.9 \
  --set auth.password="$REDIS_PASSWORD" \
  --wait --timeout 120s

# Install Kafka — plain manifest, NOT a Helm chart
kubectl apply -f infra/k8s/infra/kafka.yaml
kubectl rollout status deployment/kafka --namespace chatbox-infra --timeout=120s
```

Verify:
```bash
kubectl get pods -n chatbox-infra
# All pods should be Running and Ready (1/1)
```

### Step 5: Apply Secrets

```bash
bash infra/k8s/scripts/generate-secrets.sh
```

This creates K8s Secret objects from your environment variables. If you haven't created a `infra/k8s/secrets.env` file, it uses the defaults from `infra/k8s/base/secrets.env.example`.

### Step 6: Run Init Jobs

```bash
# Delete any previous runs first (jobs are not re-runnable by default)
kubectl delete job db-init kafka-init --namespace chatbox --ignore-not-found

# Apply init jobs (create 4 databases + tables, create Kafka topics)
kubectl apply -f infra/k8s/jobs/db-init-job.yaml
kubectl apply -f infra/k8s/jobs/kafka-init-job.yaml

# Wait for completion
kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s
```

Verify:
```bash
kubectl get jobs -n chatbox
# Both jobs should show COMPLETIONS: 1/1
```

### Step 7: Build Docker Images

```bash
# Option A: script (builds all 5 and loads into kind)
bash infra/k8s/scripts/build-images.sh

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

### Step 8: Deploy Application

```bash
kubectl apply -k infra/k8s/overlays/dev

# Re-apply secrets immediately after — the base manifests contain CHANGE_ME
# placeholders that kustomize will have just overwritten your real secrets with
bash infra/k8s/scripts/generate-secrets.sh
```

Verify:
```bash
kubectl get pods -n chatbox
# Wait for all pods to show Running and Ready (1/1)
# Init containers run first — this may take 1-2 minutes
```

### Step 9: Access the App

- **Frontend:** http://localhost:30000
- **API:** http://localhost:30080
- **Grafana:** http://localhost:30030 (admin / admin)
- **Test the API:** `curl http://localhost:30080/auth/ping`

---

## Resource Commands Reference

All commands below are organized by Kubernetes resource type. Replace `<pod-name>` with the actual pod name from `kubectl get pods -n chatbox`.

---

### Pods

A **Pod** is the running instance of your container. Deployments manage pods — you normally don't create pods directly.

```bash
# List all app pods and their status
kubectl get pods -n chatbox

# List infrastructure pods (Postgres, Redis, Kafka)
kubectl get pods -n chatbox-infra

# List monitoring pods (Prometheus, Grafana)
kubectl get pods -n chatbox-monitoring
```

Reading the output:
```
NAME                              READY   STATUS    RESTARTS   AGE
auth-service-7d8f9b6c4d-x2k9p    1/1     Running   0          5m
│                                  │       │         │
│                                  │       │         └── Times the container crashed and restarted
│                                  │       └── Running = healthy, CrashLoopBackOff = broken
│                                  └── Ready containers / Total containers (1/1 = good)
└── Deployment name + random pod ID
```

```bash
# Show full details of a pod (resources, env vars, events, probe status)
kubectl describe pod <pod-name> -n chatbox

# Tail live logs for all pods of a service
kubectl logs -f -l app.kubernetes.io/name=auth-service -n chatbox --max-log-requests=10

# Logs for a specific pod
kubectl logs <pod-name> -n chatbox

# Logs from before the last crash (when pod keeps restarting)
kubectl logs <pod-name> -n chatbox --previous

# Init container logs (runs before the app starts — migration, wait-for-db, etc.)
kubectl logs <pod-name> -n chatbox -c wait-for-postgres
kubectl logs <pod-name> -n chatbox -c run-migrations

# Open an interactive shell inside a running pod
kubectl exec -it deployment/auth-service -n chatbox -- /bin/sh

# Run a single command inside a pod without opening a shell
kubectl exec deployment/auth-service -n chatbox -- env | grep DATABASE
```

---

### Deployments

A **Deployment** tells Kubernetes: "keep N copies of this container running, and roll out updates without downtime."

```bash
# List all deployments and how many replicas are running
kubectl get deployments -n chatbox

# Show full config: replicas, image, resource limits, probes, env vars
kubectl describe deployment/auth-service -n chatbox

# Trigger a zero-downtime rolling restart (e.g. after a config change)
kubectl rollout restart deployment/auth-service -n chatbox

# Wait for the restart to finish before running the next command
kubectl rollout status deployment/auth-service -n chatbox

# See the history of past deploys
kubectl rollout history deployment/auth-service -n chatbox

# Roll back to the previous version
kubectl rollout undo deployment/auth-service -n chatbox

# Temporarily scale to more replicas (overrides kustomize — reverted on next apply)
kubectl scale deployment/chat-service --replicas=3 -n chatbox
```

---

### Services

A **Service** is a stable DNS name and IP address that routes traffic to pods. Pods come and go (they restart, scale), but the service address stays the same.

```bash
# List all services and their type + ports
kubectl get svc -n chatbox
```

Reading the output:
```
NAME    TYPE       CLUSTER-IP     EXTERNAL-IP  PORT(S)
kong    NodePort   10.96.45.12    <none>       80:30080/TCP
│       │                                      │
│       │                                      └── internal:external port
│       └── NodePort = reachable from outside the cluster on that port
└── This is the DNS name other pods use to reach this service
```

```bash
# Show full details: selector, endpoints, port config
kubectl describe svc/kong -n chatbox

# Test that a service is reachable from inside another pod
kubectl exec deployment/auth-service -n chatbox -- \
  wget -q -O- http://chat-service:8003/health
```

---

### PersistentVolumeClaims (PVCs)

A **PVC** is a request for disk storage that survives pod restarts. Only `file-service` uses one — it stores uploaded files.

```bash
# Check if the PVC is bound (STATUS should be Bound, not Pending)
kubectl get pvc -n chatbox

# Show details: storage class, size, which pod is using it
kubectl describe pvc/file-uploads-pvc -n chatbox
```

> If STATUS is `Pending`, the cluster can't provision storage. Run `kubectl get storageclass` to check what's available.

---

### ConfigMaps

A **ConfigMap** holds non-sensitive configuration (URLs, feature flags, ports). Think of it as the `.env` file for non-secret values.

```bash
# List all ConfigMaps in the app namespace
kubectl get configmaps -n chatbox

# View the contents of a ConfigMap
kubectl get configmap chatbox-shared-config -n chatbox -o yaml

# Edit a ConfigMap in-place
kubectl edit configmap chatbox-shared-config -n chatbox
```

> **Important:** Pods do NOT automatically pick up ConfigMap changes. After editing, you must restart the affected services:
```bash
kubectl rollout restart deployment/auth-service -n chatbox
kubectl rollout restart deployment/chat-service -n chatbox
```

---

### Secrets

A **Secret** holds sensitive values (passwords, tokens, database URLs). Stored as base64-encoded strings in etcd — not encrypted by default, so treat them carefully.

```bash
# List all secrets
kubectl get secrets -n chatbox

# Decode and print a single secret value
kubectl get secret auth-service-secrets -n chatbox \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d

# Decode the admin username
kubectl get secret auth-admin-secret -n chatbox \
  -o jsonpath='{.data.ADMIN_USERNAME}' | base64 -d

# Regenerate all secrets from infra/k8s/secrets.env (safest way to update)
bash infra/k8s/scripts/generate-secrets.sh
```

---

### Jobs

A **Job** runs a container once to completion and stops. We use them for database setup (`db-init`) and Kafka topic creation (`kafka-init`).

```bash
# Check if init jobs completed successfully (COMPLETIONS should be 1/1)
kubectl get jobs -n chatbox

# Read the output of the db-init job (shows which databases were created)
kubectl logs job/db-init -n chatbox

# Read the output of the kafka-init job (shows which topics were created)
kubectl logs job/kafka-init -n chatbox

# Re-run jobs (must delete first — K8s won't re-run a completed job)
kubectl delete job db-init kafka-init -n chatbox --ignore-not-found
kubectl apply -f infra/k8s/jobs/db-init-job.yaml
kubectl apply -f infra/k8s/jobs/kafka-init-job.yaml
kubectl wait --for=condition=complete job/db-init --namespace chatbox --timeout=120s
kubectl wait --for=condition=complete job/kafka-init --namespace chatbox --timeout=120s
```

---

### HorizontalPodAutoscaler (HPA) — prod overlay only

An **HPA** watches CPU/memory usage and automatically adds or removes pod replicas. Only active in the `prod` and `prod-kind` overlays.

```bash
# Check HPA status — TARGETS shows current CPU vs threshold
kubectl get hpa -n chatbox
# NAME               TARGETS   MINPODS   MAXPODS   REPLICAS
# chat-service-hpa   0%/70%    3         10        3
# ↑ at 0% CPU now, threshold is 70%, keeps 3-10 replicas

# Full details: current metrics, conditions, recent scaling events
kubectl describe hpa chat-service-hpa -n chatbox
```

> The HPA only works if `metrics-server` is installed. For kind: `kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`

---

### PodDisruptionBudgets (PDB) — prod overlay only

A **PDB** prevents Kubernetes from taking too many pods offline at once during cluster maintenance or rolling restarts. Only active in `prod` and `prod-kind`.

```bash
# List PDBs (one per service in prod)
kubectl get pdb -n chatbox

# Show details: how many pods must stay up, current status
kubectl describe pdb auth-service-pdb -n chatbox
```

---

### Events

**Events** are K8s's log of what happened — pod scheduled, image pulled, container started, OOMKilled, etc. The first place to look when something is broken.

```bash
# All recent events, newest last
kubectl get events -n chatbox --sort-by='.lastTimestamp' | tail -20

# Only warnings (errors, failures, OOMKilled)
kubectl get events -n chatbox --field-selector type=Warning

# Events for infrastructure namespace
kubectl get events -n chatbox-infra --sort-by='.lastTimestamp' | tail -10
```

---

### Resource Usage

```bash
# CPU and memory per pod (requires metrics-server to be installed)
kubectl top pods -n chatbox
kubectl top pods -n chatbox-infra

# CPU and memory of the cluster node itself
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
bash infra/k8s/scripts/generate-secrets.sh

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

The monitoring stack is **included in `make k8s-setup-local`** — you don't need to install it separately for a local cluster.

If you need to install it on its own (e.g., you already have a cluster with infra running):

```bash
make k8s-monitoring-setup
```

This installs Prometheus (metrics collection) and Grafana (dashboards).

> **Why monitoring must come before infra:** The PostgreSQL and Redis Helm charts have `metrics.serviceMonitor.enabled: true` in their Helm values, which creates `ServiceMonitor` custom resources. The `ServiceMonitor` CRD is installed by the Prometheus Operator (part of `kube-prometheus-stack`). If you install Postgres/Redis before the monitoring stack, Helm fails with `no matches for kind "ServiceMonitor"`.


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
kubectl apply -f infra/k8s/jobs/db-init-job.yaml
kubectl apply -f infra/k8s/jobs/kafka-init-job.yaml
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
# Edit infra/k8s/overlays/dev/kustomization.yaml to add resource patches
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
kubectl delete -k infra/k8s/overlays/dev
```

### Remove Only Monitoring

```bash
helm uninstall monitoring --namespace chatbox-monitoring
```

---

## Reference

### All Makefile Targets

See [Running via Makefile](#running-via-makefile) above for the essential K8s targets, or see [Makefile Reference](makefile-reference.md) for the full categorised command reference.

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
infra/k8s/
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
