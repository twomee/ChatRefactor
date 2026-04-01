# cHATBOX Documentation

## Where to Start

| I want to... | Go to |
|--------------|-------|
| **Run this project for the first time** | [Getting Started](getting-started.md) |
| **Understand how the system is designed** | [Architecture Overview](architecture/overview.md) |
| **Understand how features work** | [Feature Design Decisions](architecture/features.md) |
| **Understand the frontend architecture** | [Frontend Architecture](architecture/frontend.md) |
| **Learn the development workflow (CI/CD, linting, testing)** | [Development Workflow](development/dev-workflow.md) |
| **Run with Docker Compose (production)** | [Docker Compose Operations](operations/docker-compose.md) |
| **Run on Kubernetes** | [K8s Guide](operations/kubernetes-guide.md) / [K8s Commands](operations/kubernetes-commands.md) |
| **Set up or check monitoring** | [Monitoring](operations/monitoring.md) |
| **Look up a Make target** | [Makefile Reference](operations/makefile-reference.md) |
| **Review security audit findings** | [Security Audit](security/security-audit-2026-03.md) |

## Documentation Structure

```
docs/
├── getting-started.md                 # Clone → running in 5 minutes
├── architecture/
│   ├── overview.md                    # Tech decisions — why we chose each technology
│   ├── features.md                    # Feature design — how each feature works and why
│   └── frontend.md                    # Frontend architecture — React, hooks, state, components
├── development/
│   └── dev-workflow.md                # CI/CD, linting, testing, pre-commit, branch protection
├── operations/
│   ├── docker-compose.md              # Running & troubleshooting with Docker Compose
│   ├── kubernetes-guide.md            # K8s concepts & architecture
│   ├── kubernetes-commands.md         # K8s commands, operations & troubleshooting
│   ├── makefile-reference.md          # All Make targets
│   ├── monitoring.md                  # Prometheus, Grafana, dashboards
│   └── verification-checklist.md      # 174-check verification list
├── security/
│   ├── security-audit-2026-03.md      # Master audit summary (42 findings)
│   └── phase-1-through-6 audits       # Per-service detailed findings
└── archive/
    ├── agent-refactor.md              # Monolith → microservices refactor log
    └── sanity-check.md                # Post-refactor sanity check results
```
