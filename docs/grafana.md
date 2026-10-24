# Grafana Cloud configuration

Instance: `https://azurepopcorn464.grafana.net`. Everything below is applied from files in this repo by
`scripts/grafana_lab.py`, so it can be reviewed and re-applied.

## What is configured

| Object | Where | Source in repo |
|---|---|---|
| Restart alert `KAOP Lab - API Container Restarts` (UID `cg254gvwpyjggf`) | Folder *Komodor Demo*, group `kaop-demo-1m`, evaluated every 60 s, pending 1 m | `monitoring/alert-rule.json` |
| Dashboard *KAOP Lab* (`/d/kaop-lab`) | Folder *Komodor Demo* | `monitoring/dashboard.json` |
| KAOP contact point and route | **Not configured yet.** Added on access day with the real endpoint | `grafana_lab.py connect-kaop` |

## Change log

### 2026-10-24 17:23 UTC: restart alert carries workload identity (approved)

| Field | Before | After |
|---|---|---|
| Query A | `sum(increase(kube_pod_container_status_restarts_total{…container="api"}[10m]))`, a single unlabelled number | `sum by (cluster, namespace, pod, container) (…)`, one series per pod |
| Labels | none | `kaop=incident`, `severity=critical`, `kind=Deployment`, `deployment=kaop-api`, `service=kaop-api`, `team=sre` |
| Summary | "Python API container restarts detected in kaop-demo" | "kaop-api container restarting in namespace kaop-demo" |
| Description | Told the investigator to check probes and deployment changes, which leads the RCA | States the symptom only: restart count, pod, and the resource to investigate |
| No data | `NoData`, which would fire. The 02:13 UTC scrape gap did. | `OK`, so a monitoring gap does not start a KAOP investigation |
| Execution error | `Error` | `KeepLast` |
| Unchanged | | UID, title, folder, group, 60 s interval, 1 m pending, threshold `> 0` |

Verification at 17:23:40 UTC: health `ok`, no evaluation error, state Normal. The instance labels are `cluster`,
`namespace`, `pod`, `container`, `deployment`, `kind`, `service`, `severity`, `team` and `kaop`.

### 2026-10-24 17:24 UTC: KAOP Lab dashboard (approved)

| Panel | Query |
|---|---|
| API restarts, last 10 min | Same signal as the alert |
| Redis available, API available | `kube_deployment_status_replicas_available` |
| Restart alert | Alert list filtered to the lab rule |
| API restarts per pod | The alert query, per pod |
| Available replicas | Both Deployments over time |
| Kubernetes events in kaop-demo | Loki `{cluster="kaop-demo",namespace="kaop-demo",source="kubernetes-events"}` |

Verification: every panel query returned data, refresh every 10 s, last 30 minutes.

## Not changed

The ~120 rules installed by Grafana's Kubernetes integration, the root notification policy (receiver `empty`),
the existing `grafana-insight-processor` contact point, datasources, collectors and credentials.

## Rollback

Local snapshots, not committed:

- `artifacts/grafana/rollback-20261024T171512Z/` holds the full alerting configuration and 24 hours of state history before any change.
- `artifacts/grafana/rule-before-20261024T172309Z.json` holds the exact rule replaced by `apply-rule`.

To restore the rule, `PUT` that JSON back to `/api/v1/provisioning/alert-rules/cg254gvwpyjggf`. To remove the
dashboard, `DELETE /api/dashboards/uid/kaop-lab`.

## Alert history worth knowing

| UTC (Oct 24) | Episode |
|---|---|
| 02:13 → 03:49 | NoData during a scrape gap; now suppressed by `noDataState: OK` |
| 06:35 → 06:51 | Earlier rehearsals, one episode for two runs |
| 15:34 → 15:44 | Host stall with correct probes; fixed with 3 s probe timeouts |
| 16:41 → 16:52 | A failed deploy during tooling work |
| 16:54 → 17:07 | Incident rehearsal: Pending 110 s and Alerting 170 s after the outage began |

## Access day

```bash
ADMIN=~/.config/claude-grafana-admin/token
python3 scripts/grafana_lab.py connect-kaop --dry-run --token-file $ADMIN   # review
python3 scripts/grafana_lab.py connect-kaop --token-file $ADMIN             # contact point + route for kaop=incident
python3 scripts/grafana_lab.py test-kaop --token-file $ADMIN
```

KAOP's Grafana Investigator should use its own **Viewer** service-account token, not this admin token.
