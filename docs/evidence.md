# Evidence

All runs used `scripts/demo.sh outage` on the lab's single-node kind cluster: the probe comparison on 2026-10-24,
the KAOP rehearsals on 2026-10-25. Raw evidence for each run is kept locally under `artifacts/incidents/<run-id>/` and is not committed: baseline, first restart, events,
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

## KAOP end to end (2026-10-25)

Two full rehearsals on the KAOP workspace, each started by `scripts/demo.sh outage`.

| Step | Rehearsal 1 | Rehearsal 2 |
|---|---|---|
| Grafana alert fires (after Redis went down) | +3:26 | +3:09 |
| KAOP incident opened | Same second as the alert | Same second as the alert |
| Kubernetes RCA finished | +5:41 | +7:05 |
| Orchestrator verdict | +8:19, confidence 0.78 | +9:34, confidence 0.85 |
| Remediation options ready for a person | about +11:30 | +13:36 |
| Code Reviewer comment after the PR was opened | 35 s ([PR #1](https://github.com/chizeni24/komodor-production-lab/pull/1)) | 33 s ([PR #2](https://github.com/chizeni24/komodor-production-lab/pull/2)) |
| API Ready after Redis returned | 27.8 s | 217.7 s (restart back-off after 8 kills) |

What the agents concluded:

- **Kubernetes RCA:** trigger, Redis scaled to 0; root cause, liveness and readiness both probe `/readyz`, so a Redis
  outage becomes repeated container kills (exit 137). High confidence, every tool call a read.
- **Grafana Investigator:** ruled out OOM and CPU limits from metrics, and found the same pattern earlier in the day.
  In rehearsal 1 it suggested CPU throttling; the orchestrator rejected that as weaker than the direct cluster evidence.
- **Remediation:** restore Redis now (with undo and a verification check); decouple liveness from Redis as the durable
  fix; find what keeps scaling Redis down.
- **After a person applied the fix,** KAOP stopped the run for review rather than record a change no agent made.

Gateway boundary: asked to create a Grafana annotation, the Grafana Investigator was refused by KAOP's gateway with
"Tool 'grafana-cloud_create_annotation' is not permitted."

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
