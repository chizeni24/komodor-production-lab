# Evidence

All runs used `scripts/demo.sh outage` on the lab's single-node kind cluster, on 2026-10-24. Raw evidence for each
run is kept locally under `artifacts/incidents/<run-id>/` and is not committed: baseline, first restart, events,
pod states, ReplicaSets, and current and previous container logs.

## Same Redis outage, both probe configurations

| | Liveness on `/readyz` (bad rollout) | Liveness on `/healthz` (fix) |
|---|---|---|
| Run | `20261024T165250Z-2236b0` | `20261024T164427Z-679476` |
| Redis outage | 16:52:50 → 16:58:11 UTC (≈5 min) | 16:44:28 → 16:47:03 UTC (≈2.5 min) |
| Liveness HTTP 503 events | Yes | None |
| Liveness kills of a healthy API process | 5 (`Container api failed liveness probe, will be restarted`) | 0 |
| API restart count increase | +4 by the end of the window | 0 |
| Grafana restart alert | Normal → Pending at +111 s, Alerting at +175 s | Stayed Normal |
| API Ready after Redis returned | 4.8 s | 6.5 s |

What the numbers mean:

- **The defect does not cause the outage; Redis does.** In both runs readiness failed and the API received no traffic while Redis was down. That is correct behaviour.
- **The defect kills a healthy process repeatedly.** Each kill drops in-flight work and cold-starts the process. The restart alert then pages the API owners for a problem that lives in Redis.
- **Recovery after Redis returns is luck-dependent with the defect.** Kubernetes waits a back-off between restarts of 10 s, doubling up to 5 minutes. This run's 4.8 s recovery happened because Redis returned while the container was between back-offs. With liveness on `/healthz` there is no back-off to hit.
- **The fix is verified by the same experiment**: zero liveness failures and zero restarts.

## What an investigator can see

From the bad-probe run's `before-restore` snapshot, the evidence a correct RCA should cite:

- Events on the API pod: `Liveness probe failed: HTTP probe failed with statuscode: 503` (6×), `Readiness probe failed ... 503` (19×), `Container api failed liveness probe, will be restarted` (5×).
- The Deployment and current ReplicaSet show liveness `httpGet /readyz`. Earlier ReplicaSets show `/healthz`, which is the change.
- Redis Deployment at 0 available replicas; no Ready endpoints for the `redis` Service.
- The previous API container log: `ERROR Redis connection failed ... ConnectionRefusedError`, logged from the `/readyz` handler.
- The ConfigMap with `app.py`, readable through the `view` role, shows `/readyz` pings Redis and `/healthz` does not.

## Agent RBAC, verified before access

`scripts/verify-agent-rbac.sh` against KAOP's self-hosted agent chart (`agentops-agent-base` 0.1.2320, `rbac.create=true`,
defaults otherwise), applied to a throwaway namespace and then deleted:

| Action | Allowed |
|---|---|
| get pods, list events, get pods/log, get deployments and replicasets in `kaop-demo`; list nodes | yes |
| get secrets, create pods/exec, delete pods, patch deployments, scale deployments, create deployments | no |

## Earlier runs

Two earlier bounded rehearsals ran at 06:33 and 06:38 UTC, using a previous version of the tooling with 180-second
windows. Each produced two API restarts and fresh liveness 503 events, and one Grafana alert episode covered both:
Pending at 06:35:40, Alerting at 06:36:40, Normal at 06:51:40.

At 15:33 UTC, with the correct `/healthz` probe, the API restarted twice when the lab host stalled under a browser
crash and probes timed out after 1 s. The probes now have a 3 s timeout, above the app's 2 s Redis timeout. The
runbook keeps the presenting browser lean.
