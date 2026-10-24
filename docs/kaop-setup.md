# KAOP setup (access day)

About 90 minutes, in dependency order. Each step names the KAOP docs page it follows
([docs.komodor.com](https://docs.komodor.com)). If the in-product docs at kaop.komodor.com/docs differ,
the product wins.

## 0. Ask Komodor before access day

Several catalog agents are "enabled per account". Ask the recruiting contact to confirm the workspace has:

- Catalog agents: `kubernetes-rca`, `grafana-investigator`, `code-reviewer`, `github-file-finder` (GitHub Agent), `remediation`, `workflow-orchestrator`.
- The *Incident management & troubleshooting* module.
- Approvals for tool calls. Without them, the GitHub Agent refuses to open a PR rather than opening an unapproved one.

## 1. Grafana (already prepared)

The alert labels and the *KAOP Lab* dashboard are already applied (see [grafana.md](grafana.md)). The lab admin
token at `~/.config/claude-grafana-admin/token` handles routing on access day. One token is still needed:

| Service account | Role | Used by | Where the token goes |
|---|---|---|---|
| `kaop-grafana-investigator` | Viewer | KAOP's Grafana Investigator | KAOP's Grafana Cloud connection; keep a copy in a password manager |

## 2. Sign in and prove the loop

Follow [Quickstart](https://docs.komodor.com/get-started/quickstart.md). Run the built-in assistant once and read
the run's evidence page. This is the "every run records inputs, tool calls, reasoning, output and cost" screen.

## 3. Connect integrations

See [Integrations list](https://docs.komodor.com/manage-your-agents/build/built-in-integrations.md).

- **GitHub.** Press *Install GitHub*. Choose *only* `chizeni24/komodor-production-lab`. The GitHub Agent needs read and write on contents and pull requests; the Code Reviewer needs read access plus PR comments. Screenshot the permission page; it is governance evidence.
- **Grafana Cloud.** Use URL `https://azurepopcorn464.grafana.net` and the Viewer token from step 1.

## 4. Deploy the Kubernetes RCA agent (self-hosted)

See [Kubernetes catalog](https://docs.komodor.com/manage-your-agents/build/catalog/kubernetes.md).

1. Go to Add agent, then Browse catalog, then **Kubernetes RCA**. Name it `kubernetes-rca-kaop-demo`, putting the cluster in the name as the wizard recommends.
2. At activation, the wizard shows a worker token, once, plus a Helm command and values file. Save the values file outside git as `~/kaop/rca-values.yaml`.
3. Before installing, confirm in the values file that `rbac.create: true`, `rbac.secrets.read: false`, and `rbac.exec.namespaces: []` with `clusterWide: false`. That means no exec, which keeps the agent strictly read-only.
4. Install into its own namespace:
   ```bash
   export KUBECONFIG=$HOME/.kube/kaop-demo-rootful.yaml
   kubectl --context kind-kaop-demo create namespace kaop-agents
   helm --kube-context kind-kaop-demo install <command from the wizard> -n kaop-agents -f ~/kaop/rca-values.yaml
   kubectl --context kind-kaop-demo -n kaop-agents get pods
   ```
5. Prove the boundary, and keep the output for the governance slide:
   ```bash
   kubectl --context kind-kaop-demo -n kaop-agents get sa          # find the agent's ServiceAccount
   ./scripts/verify-agent-rbac.sh kaop-agents <service-account> artifacts/agent-rbac.txt
   ./scripts/demo.sh preflight                                     # node still healthy (agent requests 320Mi)
   ```
6. In KAOP, run it once by hand with input `{"kind":"Deployment","name":"kaop-api","namespace":"kaop-demo"}`. Expect a healthy verdict while Redis is up.

## 5. Deploy the cloud agents

See [Use specialized agents](https://docs.komodor.com/manage-your-agents/build/use-specialized-agents.md).
Deploy each to Komodor cloud: **Grafana Investigator** (bind the Grafana connection), **Remediation**, **GitHub Agent**
(bind GitHub; you are its approver), **Code Reviewer** (bind GitHub), and **Workflow Orchestrator** if the account
does not already have one holding the `step-orchestrator` role.

## 6. Create the alert endpoint and connect Grafana

See [Triggers & schedules](https://docs.komodor.com/manage-your-agents/build/triggers-schedules.md).

1. Go to Integrations, then Endpoints (inbound), then create `grafana-kaop-lab` with bearer-token authentication. **Leave routing empty for now.** The URL and token are shown once:
   ```bash
   ( umask 077; read -rsp 'URL: ' U; printf '%s\n' "$U" > ~/.config/komodor-secrets/kaop-endpoint-url ); echo
   ( umask 077; read -rsp 'Token: ' T; printf '%s\n' "$T" > ~/.config/komodor-secrets/kaop-endpoint-token ); echo
   ADMIN=~/.config/claude-grafana-admin/token
   python3 scripts/grafana_lab.py connect-kaop --dry-run --token-file $ADMIN
   python3 scripts/grafana_lab.py connect-kaop --token-file $ADMIN   # webhook contact point + route for kaop=incident
   python3 scripts/grafana_lab.py test-kaop --token-file $ADMIN      # Grafana sends a test notification
   python3 scripts/grafana_lab.py status
   ```
   If KAOP gives a URL that already embeds its token, use `connect-kaop --auth none`.
2. In the endpoint's **Test & mapping** step, confirm the captured payload shows `commonLabels.deployment=kaop-api`, `namespace=kaop-demo` and `kind=Deployment`. Map those to the investigation input if the UI asks.

## 7. Build the incident workflow

See [Incident management](https://docs.komodor.com/modules-and-workflows/sre/incidents.md) and
[Orchestrator](https://docs.komodor.com/manage-your-agents/build/catalog/orchestrator.md).

1. Go to Modules, then Overview, then enable *Incident management & troubleshooting*.
2. In *Production Alert Investigation*:
   - **Source** is the `grafana-kaop-lab` endpoint.
   - **Investigation** binds `kubernetes-rca-kaop-demo` and Grafana Investigator.
   - **Remediation** binds Remediation, then GitHub Agent.
3. Activate it. Activation is blocked until an investigation specialist is bound.

## 8. Bind the code-review workflow

See [Code Review](https://docs.komodor.com/manage-your-agents/build/catalog/code-review.md).
Bind the repository to the Code Reviewer's review workflow. Nothing needs to be committed to the repo; the GitHub
App installation is the whole requirement.

## 9. Governance settings to show

- **Approvals.** On the GitHub Agent, go to Permissions. The PR tool must be set to **ask**, and the approver list is you. See [Approvals](https://docs.komodor.com/security-and-governance/controls/approvals.md).
- **Budgets.** Go to Cost, then Agent budgets, and set a small daily budget per agent. See [Agent spend](https://docs.komodor.com/manage-your-agents/optimize/agent-spend-attribution.md).
- **Access explorer.** In Settings, use Effective access for each agent. See [Access explorer](https://docs.komodor.com/security-and-governance/identity-and-access/access-explorer.md).
- **Audit log.** Confirm agent deploys and policy changes appear. See [Audit log](https://docs.komodor.com/security-and-governance/controls/audit-log.md).

## 10. Full rehearsal (record it)

```bash
python3 scripts/grafana_lab.py status                 # restart alert must be Normal
./scripts/demo.sh outage --approve-live-mutation      # Ctrl-C once the RCA has finished
```

1. Watch for Grafana *Alerting*, then a KAOP incident, two investigation runs, and a Remediation decision.
2. Approve the PR in **Attention**. Confirm the GitHub Agent's PR appears, followed by a Code Reviewer comment.
3. Record timings: outage start, Alerting, incident created, RCA finished, PR opened, review posted.
4. Screenshot the incident, the RCA findings, the approval, the PR comment and the audit log for backup slides.
5. **Close the rehearsal PR without merging.** The GitHub Agent will not open a second PR for the same change while one is open.
6. Wait for the alert to return to Normal, at least 15 minutes, before the next run.

If the GitHub Agent is not available, open the prepared human fix instead and let the Code Reviewer review it:

```bash
gh pr create --repo chizeni24/komodor-production-lab --base main --head fix/liveness-healthz \
  --title "Decouple API liveness from Redis" --body-file docs/fix-pr-body.md
```
