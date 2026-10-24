# KAOP incident lab: one bad rollout, two governed workflows

A small Kubernetes lab for demonstrating the
[Komodor Agentic Operations Platform](https://docs.komodor.com/get-started/overview.md) (KAOP) to a platform
engineering team. A Grafana Cloud alert starts a KAOP incident investigation. A pull request starts a separate
KAOP code review. Every agent runs with its own identity, least-privilege access, a human approval before any
change, and a recorded run.

## The scenario

- **Service.** A Python API (`app.py`) serves requests from Redis. `/healthz` reports that the process is alive. `/readyz` reports that Redis answers.
- **Latent defect.** The latest commit on `main` points the API's liveness probe at `/readyz`. It looks reasonable and passes CI, because nothing goes wrong while Redis is healthy. The defect is deliberate: it models a well-intentioned bad rollout.
- **Incident.** Redis becomes unavailable. Readiness fails, which is correct. Liveness fails too, so Kubernetes kills a healthy API process again and again, five times in a five-minute rehearsal. The restart alert then pages the API owners for a problem that lives in Redis.
- **Expected finding.** Trigger: Redis outage. Root cause of the restarts: liveness coupled to a dependency. Fix: liveness → `/healthz`, a one-line change in `k8s/api.yaml`.

Measured with and without the fix: [docs/evidence.md](docs/evidence.md).

## The two KAOP workflows

| | Incident investigation | Code review |
|---|---|---|
| Trigger | Grafana Cloud restart alert → KAOP inbound endpoint | Any push to a pull request on this repo |
| Agents | Kubernetes RCA (in-cluster, read-only) and Grafana Investigator, then Remediation, then GitHub Agent | Code Reviewer |
| Can change | One PR for one config value, only after a person approves | One review comment per commit |
| Cannot | Write to the cluster, read Secrets, exec into pods, merge | Approve or merge |

Design and boundaries: [docs/architecture.md](docs/architecture.md).

## Repository map

| Path | What it is |
|---|---|
| `app.py`, `k8s/` | The service and its manifests; `k8s/api-configmap.yaml` is generated from `app.py` |
| `scripts/demo.sh` | Operator CLI: `preflight`, `deploy --ref`, `outage`, `evidence`, `reset` |
| `scripts/grafana_lab.py`, `monitoring/alert-rule.json` | Alert identity labels and routing to KAOP |
| `scripts/verify-agent-rbac.sh` | Proves what the agent's Kubernetes identity can and cannot do |
| `docs/kaop-setup.md` | Step-by-step KAOP configuration |
| `docs/runbook.md` | Presenter runbook and fallbacks |
| `docs/presentation/` | Customer deck and talk track |

## Run it

Prerequisites: a kind cluster named `kaop-demo`, kubectl, git, Python 3.9 or later, and Grafana Cloud Kubernetes
Monitoring installed with cluster name `kaop-demo`.

```bash
./scripts/demo.sh deploy --ref origin/main --approve-live-mutation   # apply k8s/ exactly as in git
./scripts/demo.sh preflight                                          # read-only health check
./scripts/demo.sh outage --approve-live-mutation                     # Redis outage; Ctrl-C restores Redis
```

Every command that changes the cluster requires `--approve-live-mutation`. The CLI only touches the `kaop-demo`
namespace, never reads Secrets, and refuses any other kubeconfig context.

Development checks (CI runs the same):

```bash
python3 -m pip install PyYAML==6.0.2
python3 -B scripts/sync-configmap.py --check
python3 -B -m unittest discover -s tests -v
```
