# Presenter runbook

Present from your **laptop**: slides, KAOP, Grafana and GitHub in its browser. Run lab commands over SSH on the
lab host. Keep browsers off the lab host; a browser crash there stalled the node once and caused false probe
failures.

```bash
ssh node01@<lab-host>          # same LAN: 192.168.1.116; otherwise a Tailscale address
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
- Open these tabs on the laptop:
  1. The deck.
  2. KAOP: Incidents, Attention, the Kubernetes RCA agent's Permissions, and the Audit log.
  3. The Grafana alert rule.
  4. GitHub pull requests.
  5. Backup slides with the screenshots from the rehearsal.

## Live

| Step | Do | Say (one line) |
|---|---|---|
| 1 | `./scripts/demo.sh preflight` | "Healthy, and carrying a latent defect from last week's rollout." |
| 2 | `./scripts/demo.sh outage --approve-live-mutation` | "Redis just went away. Watch what Kubernetes does to a healthy API." |
| 3 | Watch `restarts=+1 ... CrashLoopBackOff` in the terminal | "Readiness failing is right. Liveness failing is the bug." |
| 4 | Grafana tab: the rule goes Alerting, ~2 minutes after the outage | "Detection is Grafana's job. Now KAOP takes over." |
| 5 | KAOP incident: show the two investigators, findings, confidence and evidence | "Root cause, confidence and evidence, with no wall of logs." |
| 6 | Attention: approve the GitHub Agent's PR | "The agent proposes. I decide. The decision is recorded." |
| 7 | GitHub: the PR plus the Code Reviewer comment | "A separate workflow and identity. It can comment, never merge." |
| 8 | Ctrl-C in the terminal: Redis returns, and the result line prints the restart count | "Kubernetes killed a healthy process N times for a problem in Redis, and paged the wrong team." |
| 9 | Optional: merge, `deploy --ref origin/main`, then `outage --max-seconds 90` | "Same outage, zero restarts. That's the fix verified." |

**Timing.** The outage window defaults to a 600-second maximum. Press Ctrl-C as soon as the RCA has finished.
The Kubernetes RCA needs the failing pod alive to read its previous-container logs.

## Fallbacks

- **Alert still Firing from a rehearsal.** `outage` refuses to start. Wait for Normal. If you must go on, use `--skip-grafana-check`, but KAOP will not get a fresh notification.
- **KAOP slow.** Open the completed incident from the rehearsal in KAOP's incident list and walk through it. Say it is the rehearsal run.
- **GitHub Agent unavailable.** Open the prepared PR with the command at the end of [kaop-setup.md](kaop-setup.md).
- **Something stuck.** Run `./scripts/demo.sh reset --approve-live-mutation`. It restores Redis and waits for the API. It never edits the API spec.
- **Lab host unreachable.** Present the rehearsal recording and backup slides. Do not rebuild live.

## Evidence

`./scripts/demo.sh evidence` writes a sanitized snapshot to `artifacts/incidents/`. Every `outage` run also keeps
its baseline, first restart, before-restore evidence and result there.

## If the lab must move to a cloud VM

This is only needed if the lab host cannot be reached from where you present. It takes about an hour, so do it at
least a day before.

1. Create an Ubuntu VM with 4 vCPU and 16 GB. Install Docker or Podman, kind, kubectl, helm and git.
2. Run `kind create cluster --name kaop-demo`. The scripts expect context `kind-kaop-demo` and node `kaop-demo-control-plane`.
3. In Grafana Cloud, go to Kubernetes Monitoring, then Configuration. Install it with cluster name **`kaop-demo`**, so the existing alert query still matches.
4. Clone the repo, copy `~/.config/komodor-secrets/`, then run `./scripts/demo.sh deploy --ref origin/main --approve-live-mutation`.
5. Install the KAOP Kubernetes RCA agent there, as in [kaop-setup.md](kaop-setup.md) step 4.
