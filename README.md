# Komodor KAOP: one incident, two governed workflows

Published preparation branch: `prep/single-incident-demo`. Clone that branch for the complete automation and operator
documentation; default `main` intentionally remains unchanged.

```bash
git clone --branch prep/single-incident-demo https://github.com/chizeni24/komodor-production-lab.git
cd komodor-production-lab
```

A Python API talks to Redis in the existing `kaop-demo` kind cluster. A deliberate liveness misconfiguration
amplifies a Redis outage into API restarts. Grafana detects the signal; the intended KAOP workflow investigates it.
A separate fresh GitHub PR triggers the intended reviewer workflow. **Neither KAOP integration is verified yet.**

```bash
./scripts/smoke-test.sh --report artifacts/baseline.json  # safe local checks; no incident or reset
./scripts/demo.sh evidence                             # sanitized local evidence
```

Use the explicit existing kubeconfig `$HOME/.kube/kaop-demo-rootful.yaml`, context `kind-kaop-demo`, namespace `kaop-demo`.
Do not recreate the cluster or reinstall monitoring. Scripts need Python 3, kubectl and git; development checks also use PyYAML.

- [Presenter commands, approval boundaries and recovery](docs/demo-runbook.md)
- [Concise interview operator card](docs/OPERATOR_CARD.md)
- [Current acceptance and blockers](docs/prelogin-status.md)
- [Verified Grafana rule, alert history and restored read-only MCP](docs/grafana-verification.md)
- [Grafana queries and read-only verification](monitoring/queries.md)
- [Genuine remediation PR package](review-pr/README.md)
- [Revised seven-slide presentation](docs/presentation/KAOP_Customer_Pitch_REVISED.pptx) and [first-person script](docs/presentation/PRESENTATION_SCRIPT_REVISED.md)
- [Visually reviewed PDF](docs/presentation/KAOP_Customer_Pitch_REVISED.pdf) and [native visual review](docs/presentation/VISUAL_REVIEW.md)
- [Pitch review and suggestions for the other agent](docs/presentation/PITCH_REVIEW.md)
- [First five actions after KAOP login](docs/access-day-checklist.md)

Full preflight requires current Grafana verification. Incident/reset commands require explicit approval and the
`--approve-live-mutation` flag. Safe tests:

```bash
bash -n scripts/demo.sh scripts/smoke-test.sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/check-probes.py
```

The original assignment and supplied handoff are local reference inputs in `docs/KAOP_SINGLE_INCIDENT_CODEX_HANDOFF/`,
preserved locally and excluded from publication. They are not required to run the automation.
The historical memory/OOM experiment is default-disabled backup evidence, not an additional live scenario.
