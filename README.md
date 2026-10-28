# KAOP incident lab: one bad rollout, two governed workflows

A small, real Kubernetes lab that shows how the
[Komodor Agentic Operations Platform](https://docs.komodor.com/get-started/overview.md) (KAOP) lets a platform
team put AI agents on production work without losing control. Every agent has its own identity, least-privilege
access, a person's approval before any change, and a recorded run. Both workflows below run on a real KAOP
workspace and were rehearsed end to end.

## The idea

Most engineering teams already have AI agents. Support has a bot, SRE wired one to monitoring, developers added
one to pull requests. The hard part is not building agents. It is knowing who owns them, what they can touch,
and what they did.

This lab answers those questions with one realistic incident, handled end to end:

1. A well-intentioned change ships a latent bug.
2. A dependency outage exposes it.
3. Grafana Cloud alerts.
4. KAOP agents investigate and propose fixes. A person approves and applies one.
5. The durable fix goes out as a pull request, which a separate KAOP agent reviews automatically.

Every step runs under an identity, inside a boundary that something other than a prompt enforces, and leaves a
record.

**Why this incident.** A liveness probe that depends on a downstream service is a common, real misconfiguration.
It passes review and CI, hides while everything is healthy, and only shows up when the dependency blips. The fault
lives in how two components interact, not inside one function, so finding it takes real investigation.

## Architecture

```mermaid
flowchart LR
  subgraph host["Lab host: kind cluster kaop-demo"]
    direction TB
    subgraph app["namespace kaop-demo"]
      api["kaop-api<br/>Python API<br/>/healthz · /readyz"] -- PING --> redis[("redis")]
    end
    subgraph mon["namespace monitoring"]
      alloy["Grafana Alloy<br/>kube-state-metrics"]
    end
    subgraph agents["namespace kaop-agents"]
      rca["Kubernetes RCA agent<br/>read-only ServiceAccount"]
    end
  end

  subgraph grafana["Grafana Cloud"]
    prom["Prometheus · Loki"]
    rule["Restart alert<br/>+ KAOP Lab dashboard"]
  end

  subgraph kaop["KAOP, Komodor cloud"]
    ep["Inbound endpoint"]
    wf["Incident workflow<br/>+ Orchestrator"]
    gi["Grafana Investigator<br/>(gateway blocks write tools)"]
    rem["Remediation<br/>(plan-only)"]
    appr{{"Approve and apply<br/>(a person)"}}
    cr["Code Reviewer"]
    audit[("Runs, evidence<br/>and audit log")]
  end

  subgraph gh["GitHub"]
    repo["main: k8s manifests"]
    pr["Pull request<br/>+ Actions CI"]
  end

  alloy -- "metrics, events" --> prom --> rule
  rule -- "webhook, labelled with<br/>kind / deployment / namespace" --> ep --> wf
  wf --> rca & gi
  rca -.->|"reads pods, events, logs"| app
  gi -.->|reads| prom
  rca & gi --> rem --> appr
  appr -- "kubectl: restore Redis" --> app
  appr -- "opens the one-line PR" --> pr
  pr --> cr -- "review comment" --> pr
  pr -- "person merges" --> repo -- "demo.sh deploy" --> app
  wf & rem & cr --> audit
```

Every connection from the lab host is outbound: Alloy pushes telemetry to Grafana Cloud, and the in-cluster agent
dials the KAOP control plane. Nothing on the host listens on the internet.

## How the incident unfolds

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant K8s as Kubernetes
  participant G as Grafana Cloud
  participant K as KAOP
  participant P as Person
  participant GH as GitHub
  Note over K8s: main already runs liveness on /readyz (the latent bug)
  Op->>K8s: Redis outage (scale to zero)
  K8s->>K8s: readiness fails (correct), liveness fails (bug), API killed repeatedly
  G->>G: restart count rises, alert Pending then Alerting
  G->>K: webhook with kind, deployment, namespace, pod
  K->>K8s: Kubernetes RCA reads events, probes, ReplicaSets, logs
  K->>G: Grafana Investigator reads metrics and alert history
  K->>K: Orchestrator weighs both, Remediation proposes fixes
  K->>P: the workflow waits for a person to select a fix
  P->>K: approve "restore Redis"
  P->>K8s: run the proposed command (Redis back)
  P->>GH: open the one-line PR (liveness back to /healthz)
  GH->>K: PR event starts the code review workflow
  K->>GH: Code Reviewer comments, and cannot approve or merge
  P->>GH: merge
  Op->>K8s: deploy main, rerun the outage: zero restarts
```

## The scenario

| | |
|---|---|
| **Service** | A Python API (`app.py`) backed by Redis. `/healthz` says the process is alive; `/readyz` says Redis answers. |
| **Bad rollout** | The latest commit on `main` points the API's liveness probe at `/readyz`. The defect is deliberate and models a well-intentioned change. |
| **Incident** | Redis goes down. Readiness fails, which is correct. Liveness fails too, so Kubernetes kills a healthy API again and again, and the restart alert pages the API owners for a Redis problem. |
| **Finding** | Trigger: Redis outage. Root cause of the restarts: liveness depends on Redis. Fix: one line, liveness back to `/healthz`. |

```mermaid
flowchart LR
  subgraph bug["main today: liveness checks Redis"]
    direction TB
    k1["kubelet"] -- "readiness: /readyz" --> a1["kaop-api"]
    k1 -- "liveness: /readyz" --> a1
    a1 -- "PING" --> r1[("Redis down")]
    r1 -.-> o1["Both probes fail.<br/>The healthy API is killed<br/>5 times in 5 minutes"]
  end
  subgraph fix["The one-line fix: liveness checks the process"]
    direction TB
    k2["kubelet"] -- "readiness: /readyz" --> a2["kaop-api"]
    k2 -- "liveness: /healthz" --> a2
    a2 -- "PING, readiness only" --> r2[("Redis down")]
    r2 -.-> o2["Only readiness fails.<br/>No traffic until Redis is back,<br/>0 restarts"]
  end
  classDef bad fill:#fde8e8,stroke:#c0392b,color:#7b1d1d
  classDef good fill:#e6f6ee,stroke:#1e8e5a,color:#145c3a
  class o1 bad
  class o2 good
```

Measured on this lab with the same Redis outage:

| | Liveness checks Redis | Liveness checks the process |
|---|---|---|
| Times Kubernetes killed the healthy API | 5 in 5 minutes | 0 |
| Grafana restart alert | Fired after about 3 minutes | Stayed quiet |

Details: [docs/evidence.md](docs/evidence.md).

## Who can do what

Each agent's limit is enforced outside the agent, so a prompt cannot widen it:

```mermaid
flowchart LR
  rca["Kubernetes RCA"] --> rbac{{"Kubernetes RBAC"}}
  rbac --> rcaok["Can read pods, events,<br/>logs, workloads"]
  rbac -.-> rcano["Cannot: Secrets, exec,<br/>delete, patch, scale"]
  gi["Grafana Investigator"] --> gw{{"KAOP gateway allow list"}}
  gw --> giok["Can use 28 read tools:<br/>metrics, logs, alerts"]
  gw -.-> gino["Cannot: annotations,<br/>generic API calls, writes"]
  orch["Workflow Orchestrator"] --> wl{{"Worker allowlist"}}
  wl --> ook["Can call the agents<br/>bound to the workflow"]
  wl -.-> ono["Cannot call any other agent"]
  rem["Remediation"] --> plan{{"Plan-only, no credentials"}}
  plan --> rok["Can propose a fix<br/>with undo and a check"]
  plan -.-> rno["Cannot touch a live system"]
  cr["Code Reviewer"] --> app{{"GitHub App scopes"}}
  app --> crok["Can post one comment<br/>per commit"]
  app -.-> crno["Cannot approve or merge"]
  classDef no fill:#fde8e8,stroke:#c0392b,color:#7b1d1d
  classDef ok fill:#e6f6ee,stroke:#1e8e5a,color:#145c3a
  class rcano,gino,ono,rno,crno no
  class rcaok,giok,ook,rok,crok ok
```

| Agent | Can change | Enforced by |
|---|---|---|
| Kubernetes RCA, in the cluster | Nothing. Reads pods, events, logs and workloads; no Secrets, no exec | Kubernetes RBAC on its own ServiceAccount |
| Grafana Investigator | Nothing, except short links to its evidence. Reads metrics, events and alerts | KAOP gateway allow list: 28 read tools out of about 75; everything else is not found |
| Workflow Orchestrator | Nothing. Routes work between agents | Worker allowlist: it can call only the agents bound to the workflow |
| Remediation | Nothing. Proposes fixes with commands, undo and verification | Plan-only by design |
| Code Reviewer | One comment per commit; cannot approve or merge | GitHub app scopes |

The Kubernetes boundary was checked against KAOP's own agent chart with `kubectl auth can-i`
(`scripts/verify-agent-rbac.sh`): it can read pods, events and logs, and is denied Secrets, exec, delete, patch and scale.
The gateway boundary was checked by asking the Grafana Investigator to create an annotation, and later to call the
generic `grafana_api_request` tool: KAOP refused both before they reached Grafana ("Tool ... is not permitted").

Around the agents: each one carries an owner and team label, the incident workflow has a daily budget that blocks new
investigations at its cap (tested: an alert over the cap was not investigated), and a knowledge-base doc
([docs/platform-standards.md](docs/platform-standards.md)) gives the agents the team's probe policy and service facts.

KAOP also keeps the record honest: when a person applies the approved fix, the workflow stops for review and refuses
to record the change as applied by an agent.

## Against the brief

| The brief asks | Where it is |
|---|---|
| A small app with two parts, where the fault hides in how they interact | `app.py` (API) and Redis; the fault is the API's liveness probe depending on Redis |
| Code on public GitHub | This repository |
| Grafana Cloud free tier fires the alert | Restart alert routed to a KAOP endpoint ([docs/grafana.md](docs/grafana.md)) |
| A code review agent that comments on new PRs on its own, shown on a real PR | Code Reviewer comments on [PR #1](https://github.com/chizeni24/komodor-production-lab/pull/1), [PR #2](https://github.com/chizeni24/komodor-production-lab/pull/2) and [PR #3](https://github.com/chizeni24/komodor-production-lab/pull/3), the fix for this incident. On PR #3 it checked the change against the probe standard in KAOP's knowledge base. [PR #4](https://github.com/chizeni24/komodor-production-lab/pull/4) was a deliberately bad change: it requested changes with two blocking findings and failed the PR's status check, while CI passed. All were closed unmerged, so `main` keeps the bug for the next run |
| A KAOP agent on the cluster that sees pods, events and restarts | Kubernetes RCA, self-hosted in namespace `kaop-agents` |
| The alert routed into a workflow that runs without hand-holding | KAOP incident workflow: alert, investigation and proposed fixes run on their own; a person selects the fix |
| What the agent can see and touch, and what enforces it | [Who can do what](#who-can-do-what): Kubernetes RBAC, KAOP's gateway, plan-only Remediation |
| A real finding: root cause, confidence, suggested fix | Each incident's investigation and remediation output ([docs/evidence.md](docs/evidence.md)) |
| A real incident, reproduced for real | `scripts/demo.sh outage`: real pod events, logs and restart counts |
| **Optional:** more than one agent, with handoffs | Done. The orchestrator sends the alert to the Kubernetes RCA and the Grafana Investigator, weighs their evidence, and hands the result to Remediation, which proposes fixes for a person to select |
| **Optional:** a deeper Grafana Cloud integration | Done. The Grafana Investigator queries Prometheus, Loki and alert history through KAOP's gateway |
| How the pitch uses KAOP's docs and website | [References](#references): the documentation pages behind each part of the deck and demo |

## Design decisions

- **Catalog agents, not custom ones.** The Kubernetes RCA agent is built from Klaudia's root-cause knowledge, and its boundary is a Kubernetes ServiceAccount rather than a prompt.
- **A pull request, not a live patch.** Git is the source of truth. A live fix would drift from git and skip review. `scripts/demo.sh deploy` applies `k8s/` from a git ref, standing in for Argo CD or Flux.
- **Fix the probe, keep the probe.** Liveness moves to `/healthz` rather than being removed, so a genuinely stuck process is still restarted.
- **Probe timeouts above the dependency timeout.** Probes allow 3 s, the Redis client 2 s, so a slow host or dependency doesn't cause false liveness failures.
- **The alert describes the symptom, not the answer.** It carries the workload's identity and restart count, and nothing that hints at the cause.

More: [docs/architecture.md](docs/architecture.md).

## Repository map

| Path | What it is |
|---|---|
| `app.py`, `k8s/` | The service and its manifests; `k8s/api-configmap.yaml` is generated from `app.py` |
| `scripts/demo.sh` | Operator CLI: `preflight`, `deploy --ref`, `outage`, `evidence`, `reset` |
| `scripts/grafana_lab.py`, `monitoring/` | Grafana alert rule, dashboard and KAOP routing as code ([docs/grafana.md](docs/grafana.md)) |
| `scripts/verify-agent-rbac.sh` | Shows what an agent's Kubernetes identity can and cannot do |
| `scripts/lab-shortcuts.sh` | Short shell commands for the live demo (`lab-check`, `lab-break`, `lab-fix`, `lab-pr`) |
| `docs/architecture.md` | Workflows, boundaries and design choices in detail |
| `docs/evidence.md` | Measured runs: probe comparison and both KAOP rehearsals |
| `docs/kaop-setup.md` | KAOP configuration, step by step |
| `docs/platform-standards.md` | The knowledge-base doc the agents read: probe policy and service facts |
| `docs/runbook.md` | Demo runbook and fallbacks |
| `docs/presentation/` | Customer deck (PPTX and PDF) |

| Branch | Purpose |
|---|---|
| `main` | The lab, ending in the bad-rollout commit the incident exposes |
| `fix/decouple-liveness` | The one-line fix a person opens as a pull request during the demo |
| `feature/memory-leak-scenario` | An optional second fault: a gradual memory leak ending in `OOMKilled` |

## Run it

You need kind, kubectl, helm, git, the GitHub CLI (`gh`), Python 3.9 or later, a Grafana Cloud free-tier stack
and a KAOP workspace. This lab ran on kind 0.33 (Kubernetes 1.37) with rootful podman, on one 22 GB laptop.

**1. Cluster and app**

```bash
kind create cluster --name kaop-demo                                  # context kind-kaop-demo
./scripts/demo.sh deploy --ref origin/main --approve-live-mutation    # apply k8s/ exactly as it is in git
./scripts/demo.sh preflight                                           # read-only; expect LATENT DEFECT on main
```

Commands that change the cluster require `--approve-live-mutation`. The CLI only touches the `kaop-demo`
namespace, never reads Secrets, and refuses any other kubeconfig context.

**2. Grafana Cloud**

Install Grafana Cloud Kubernetes Monitoring (Helm chart `k8s-monitoring`) from the Grafana Cloud UI with cluster
name `kaop-demo`. Then apply the alert and dashboard from this repo ([docs/grafana.md](docs/grafana.md)):

```bash
python3 scripts/grafana_lab.py apply-rule                 # restart alert with workload labels
python3 scripts/grafana_lab.py apply-dashboard            # the KAOP Lab dashboard
python3 scripts/grafana_lab.py connect-kaop --dry-run     # review, then run without --dry-run
python3 scripts/grafana_lab.py status                     # expect: Normal, labels yes, KAOP route configured
```

Tokens and the KAOP endpoint URL are read from files and never printed; `--help` on each command shows the
options.

**3. KAOP**

Follow [docs/kaop-setup.md](docs/kaop-setup.md): install the Kubernetes RCA agent in `kaop-agents` with exec turned
off, connect Grafana Cloud through the gateway allow list, create the alert endpoint, the incident workflow and the
code review workflow on this repository. Then check the agent's Kubernetes access:

```bash
scripts/verify-agent-rbac.sh kaop-agents kubernetes-rca-agentops-agent-base   # writes artifacts/agent-rbac.txt
```

**4. Run the incident**

```bash
source scripts/lab-shortcuts.sh
lab-check     # read-only: app, Grafana alert, KAOP agent, free memory
lab-break     # Redis down until someone restores it (30-minute cap); restarts print as they happen
lab-fix       # the fix KAOP proposes: scale Redis back to 1
lab-pr        # open the one-line liveness fix from fix/decouple-liveness as a pull request
lab-reset     # emergency: bring Redis back and wait for the API
```

To verify the durable fix, deploy the fix branch and repeat the outage (expect zero restarts), then put the bug
back for the next run:

```bash
./scripts/demo.sh deploy --ref origin/fix/decouple-liveness --approve-live-mutation
./scripts/demo.sh outage --approve-live-mutation --max-seconds 300
./scripts/demo.sh deploy --ref origin/main --approve-live-mutation
```

The step-by-step demo, timings and fallbacks are in [docs/runbook.md](docs/runbook.md).

**After a reboot**

kind does not restart the cluster on its own. Start the node container, wait about two minutes, then run
`lab-check`:

```bash
sudo podman start kaop-demo-control-plane      # or: docker start kaop-demo-control-plane
```

If `kubectl` still says "connection refused" after a few minutes, the node's container runtime timed out on start.
Restart it:

```bash
sudo podman exec kaop-demo-control-plane bash -c 'systemctl restart containerd && systemctl restart kubelet'
```

Grafana may show NoData for a few minutes while monitoring catches up.

**Checks (CI runs the same)**

```bash
python3 -m pip install PyYAML==6.0.2
bash -n scripts/demo.sh scripts/smoke-test.sh
python3 -B scripts/sync-configmap.py --check
python3 -B -m unittest discover -s tests -v
```

## References

The KAOP documentation behind this lab, the deck and the demo. All pages are at
[docs.komodor.com](https://docs.komodor.com); [llms-full.txt](https://docs.komodor.com/llms-full.txt) is the
whole set in one file.

**The platform**

- [What KAOP is](https://docs.komodor.com/get-started/overview)
- [Concepts and glossary](https://docs.komodor.com/get-started/concepts)
- [Onboarding: the six steps](https://docs.komodor.com/get-started/onboarding)
- [Deployment methods: hosted and self-hosted agents](https://docs.komodor.com/get-started/deployment-methods)
- Build, Run, Optimize:
  [build](https://docs.komodor.com/manage-your-agents/build/how-it-works),
  [run](https://docs.komodor.com/manage-your-agents/run/how-it-works),
  [optimize](https://docs.komodor.com/manage-your-agents/optimize/how-it-works)
- [Agent catalog](https://docs.komodor.com/manage-your-agents/build/catalog/overview) and
  [importing an existing agent](https://docs.komodor.com/manage-your-agents/build/import-an-agent)

**The workflows and agents in this lab**

- [Production alert investigation (incidents)](https://docs.komodor.com/modules-and-workflows/sre/incidents)
- [Triggers: how the Grafana alert gets in](https://docs.komodor.com/manage-your-agents/build/triggers-schedules)
- [Orchestrator](https://docs.komodor.com/manage-your-agents/build/catalog/orchestrator)
- [Kubernetes RCA](https://docs.komodor.com/manage-your-agents/build/catalog/kubernetes)
- [Grafana investigator (APM)](https://docs.komodor.com/manage-your-agents/build/catalog/apm)
- [Remediation](https://docs.komodor.com/manage-your-agents/build/catalog/remediation) and
  [Remediation Executor](https://docs.komodor.com/manage-your-agents/build/catalog/remediation-executor)
- [Code Reviewer](https://docs.komodor.com/manage-your-agents/build/catalog/code-review)
- [Knowledge base](https://docs.komodor.com/manage-your-agents/build/knowledge-base) and
  [memory](https://docs.komodor.com/manage-your-agents/build/memory)

**Governance**

- [How the governance layers fit together](https://docs.komodor.com/security-and-governance/how-it-works)
- [Agent identity](https://docs.komodor.com/security-and-governance/identity-and-access/agent-identity) and
  [roles and permissions](https://docs.komodor.com/security-and-governance/identity-and-access/roles-permissions)
- [MCP Gateway: allow and deny lists](https://docs.komodor.com/security-and-governance/architecture-considerations/mcp-gateway)
- [Standards and guardrails, including budgets](https://docs.komodor.com/security-and-governance/controls/standards-guardrails)
- [Approvals](https://docs.komodor.com/security-and-governance/controls/approvals) and
  [the Attention inbox](https://docs.komodor.com/manage-your-agents/run/attention)
- [Audit log](https://docs.komodor.com/security-and-governance/controls/audit-log)
- [Secrets and credential handling](https://docs.komodor.com/security-and-governance/architecture-considerations/secrets-credential-handling),
  [data handling and redaction](https://docs.komodor.com/security-and-governance/architecture-considerations/data-handling-redaction),
  [model providers](https://docs.komodor.com/security-and-governance/architecture-considerations/providers)

**Evidence, cost and quality**

- [Runs and evidence](https://docs.komodor.com/manage-your-agents/run/runs-evidence)
- [Fleet health](https://docs.komodor.com/manage-your-agents/optimize/fleet-health)
- [Agent spend attribution: cost per run and budgets](https://docs.komodor.com/manage-your-agents/optimize/agent-spend-attribution)
- [Evaluations](https://docs.komodor.com/manage-your-agents/optimize/evaluations)

**Where a pilot could go next**

- [Alert Intelligence](https://docs.komodor.com/modules-and-workflows/sre/alert-hygiene)
- [Kubernetes Cost](https://docs.komodor.com/modules-and-workflows/cost-optimization/k8s-cost)
- [Connecting Claude Code and other coding agents](https://docs.komodor.com/developer-tools/connect-coding-agents)
