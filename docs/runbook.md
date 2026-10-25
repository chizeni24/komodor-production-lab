# Presenter runbook

Everything runs on one machine: the kind cluster, the terminal and the browser you present from. The host has
7 GB of RAM, and a browser memory spike stalled the node once (probes now allow 3 s, which absorbs short stalls).

- Use one browser with only the demo tabs open. Close other apps, editors and AI assistants before the call.
- Check free memory before you start: `free -m` should show at least 2 GB available.

```bash
cd ~/komodor-demo
```

## T-60 minutes

```bash
git pull --ff-only
./scripts/demo.sh preflight                   # expect: LATENT DEFECT: liveness ... /readyz
python3 scripts/grafana_lab.py status         # expect: Normal, workload labels yes, KAOP route configured
```

- If preflight says the probes are decoupled, a previous fix was deployed. Put the bad rollout back with `./scripts/demo.sh deploy --ref origin/main --approve-live-mutation`, assuming `main` still carries it.
- Make sure no rehearsal PR is still open.
- Open these tabs, and nothing else:
  1. The deck.
  2. KAOP: Incidents, the Grafana Investigator's guardrail-test run, and the Audit log.
  3. The Grafana *KAOP Lab* dashboard (`/d/kaop-lab`), which shows restarts, Redis, the alert and events on one screen.
  4. GitHub, on branch `fix/decouple-liveness`.
  5. Backup slides with the screenshots from the rehearsal.

## Live

Start the outage when the talk begins. The decision is ready about 13–14 minutes later, when the demo starts.

| Step | Do | Say (one line) |
|---|---|---|
| 0 | Slide 1: `./scripts/demo.sh outage --approve-live-mutation --max-seconds 1800` | "Before I start, I'm going to break something." |
| 1 | Terminal: `restarts=+N`, `CrashLoopBackOff` | "Readiness failing is right. Liveness failing is the bug." |
| 2 | *KAOP Lab* dashboard: Redis at 0, restarts climbing, alert Alerting about 3 minutes in | "Detection is Grafana's job. Then KAOP takes over." |
| 3 | KAOP incident: two investigators, root cause, confidence, evidence, tool calls | "Trigger and root cause, separated, with evidence." |
| 4 | KAOP bell → incident → select "Scale redis back to 1 replica" | "The agent proposes. I decide. The decision is recorded." |
| 5 | `kubectl scale deployment/redis -n kaop-demo --replicas=1` (the outage script then ends itself) | "I'm running the exact command KAOP proposed." |
| 6 | Incident timeline: "Workflow stopped for review" | "KAOP won't record a change no agent made." |
| 7 | GitHub: `fix/decouple-liveness` → Compare & pull request → Create; the Code Reviewer comments in about 30 s | "A separate workflow and identity. It can comment, never merge." |
| 8 | Terminal RESULT line or dashboard: API back | "The bad check delayed recovery by the restart back-off. The fix removes it." |

**Timing.** Rehearsed on 2026-10-25: alert at +3 min, root cause at +7, decision ready at +13.6, Code Reviewer
comment 33 s after the PR. With the bad check, the API took 218 s to recover after Redis returned (restart back-off).

## Fallbacks

- **Alert still Firing from a rehearsal.** `outage` refuses to start. Wait for Normal. If you must go on, use `--skip-grafana-check`, but KAOP will not get a fresh notification.
- **KAOP slow.** Open the completed incident from the rehearsal in KAOP's incident list and walk through it. Say it is the rehearsal run.
- **Decision not ready yet.** Walk through the investigation runs and their tool calls first.
- **PR not reviewed.** Check the repository is still bound in KAOP's code review workflow; push an empty commit to re-trigger.
- **Something stuck.** Run `./scripts/demo.sh reset --approve-live-mutation`. It restores Redis and waits for the API. It never edits the API spec.
- **Cluster unresponsive.** Present the rehearsal results in appendix C. Do not rebuild live.

## Evidence

`./scripts/demo.sh evidence` writes a sanitized snapshot to `artifacts/incidents/`. Every `outage` run also keeps
its baseline, first restart, before-restore evidence and result there.

## If the lab must move to a cloud VM

Only needed if this machine can't be used on the day. It takes about an hour, so do it at
least a day before.

1. Create an Ubuntu VM with 4 vCPU and 16 GB. Install Docker or Podman, kind, kubectl, helm and git.
2. Run `kind create cluster --name kaop-demo`. The scripts expect context `kind-kaop-demo` and node `kaop-demo-control-plane`.
3. In Grafana Cloud, go to Kubernetes Monitoring, then Configuration. Install it with cluster name **`kaop-demo`**, so the existing alert query still matches.
4. Clone the repo, copy `~/.config/komodor-secrets/`, then run `./scripts/demo.sh deploy --ref origin/main --approve-live-mutation`.
5. Install the KAOP Kubernetes RCA agent there, as in [kaop-setup.md](kaop-setup.md) step 4.
