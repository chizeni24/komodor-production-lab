# KAOP setup

How the KAOP workspace for this lab is configured. Most steps were done through KAOP's MCP server from a coding
agent, which KAOP records in its audit log like any other change. The docs each step follows are on
[docs.komodor.com](https://docs.komodor.com); where the product differs, the product wins.

## 1. Integrations

- **GitHub.** The KAOP GitHub App is installed on `chizeni24/komodor-production-lab` only.
- **Grafana Cloud.** Connected through KAOP's MCP gateway (server `grafana-cloud`, group `grafana-cloud-tools`).
  The group denies write, create, update, delete and exec tools, the generic `grafana_api_request` tool and
  `install_plugin`, plus tool families this stack has no data for (Tempo, Pyroscope, OnCall, Grafana's own AI and
  agent-observability tools). What remains is read-only. A name-pattern deny list is easy to get wrong: the generic API
  tool slipped past the write patterns until the agent's full tool list was read. An allow list is the stricter option.

## 2. Kubernetes RCA agent (self-hosted, read-only)

See [Kubernetes catalog](https://docs.komodor.com/manage-your-agents/build/catalog/kubernetes.md).

1. Catalog → Kubernetes RCA, cluster name `kaop-demo`. Keep the generated values file outside git.
2. The catalog default grants `pods/exec` cluster-wide. Turn it off before installing:
   ```yaml
   rbac:
     create: true
     exec:
       clusterWide: false
       namespaces: []
   ```
3. Save the worker token to a private file from your own terminal, then install. The token never appears on screen:
   ```bash
   ( umask 077; read -rsp 'Worker token: ' T; printf '%s' "$T" > ~/.config/komodor-secrets/kaop-rca-worker-token ); echo
   helm install kubernetes-rca oci://ghcr.io/komodorio/charts/agentops-agent-base --version 0.1.2350 \
     --kube-context kind-kaop-demo -n kaop-agents --create-namespace -f <values file> \
     --set-string controlplane.workerToken.value="$(cat ~/.config/komodor-secrets/kaop-rca-worker-token)"
   ```
4. Prove the boundary:
   ```bash
   ./scripts/verify-agent-rbac.sh kaop-agents kubernetes-rca-agentops-agent-base artifacts/agent-rbac.txt
   ```

## 3. Cloud agents

Deployed from the catalog to Komodor cloud: **Grafana Investigator** (bound to `grafana-cloud-tools`),
**Workflow Orchestrator**, **Remediation** (plan-only) and **Code Reviewer** (bound to the GitHub integration).

The catalog is curated per account. This workspace has no Remediation Executor or GitHub Agent, so a person applies
the approved fix and opens the pull request.

## 4. Alert endpoint and Grafana routing

1. A standalone endpoint `grafana-kaop-lab`: Grafana alert format, bearer token, dedup key `startsAt` (one incident
   per firing). Copy the token from Integrations → Endpoints → Rotate token, from your own terminal:
   ```bash
   ( umask 077; read -rsp 'Token: ' T; printf '%s\n' "$T" > ~/.config/komodor-secrets/kaop-endpoint-token ); echo
   printf '%s\n' "<endpoint URL>" > ~/.config/komodor-secrets/kaop-endpoint-url
   ```
2. Grafana contact point and route (only `kaop=incident`), then a test that opens no incident:
   ```bash
   python3 scripts/grafana_lab.py connect-kaop --dry-run --token-file "$GRAFANA_ADMIN_TOKEN_FILE"
   python3 scripts/grafana_lab.py connect-kaop --token-file "$GRAFANA_ADMIN_TOKEN_FILE"
   python3 scripts/grafana_lab.py test-kaop --token-file "$GRAFANA_ADMIN_TOKEN_FILE"
   ```

## 5. Incident workflow

See [Incident management](https://docs.komodor.com/modules-and-workflows/sre/incidents.md).

*KAOP lab: Production Alert Investigation*, human-selected template. Source: `grafana-kaop-lab`, filter
`labels.kaop = incident`. Orchestrator: Workflow Orchestrator. Investigators: Kubernetes RCA and Grafana
Investigator. Remediation: Remediation.

## 6. Code review workflow

The repository is bound to the Code Reviewer's review workflow (KAOP UI → Code review). Every push to a pull request
starts a review; the comment arrives in about 30 seconds.

## 7. Ownership, budgets and standards

- **Labels.** `owner`, `team` and, for incident agents, `service: kaop-api` on every agent (`role` labels used by the
  workflow are kept). Fleet filters by owner; KAOP roles can scope access by label.
- **Budget.** The incident workflow has a daily cap of $40 that blocks new investigations. Tested by lowering it to
  $0.01: the next alert opened an incident marked "Not investigated: the daily budget is used up".
- **Knowledge base.** [platform-standards.md](platform-standards.md) uploaded on the Knowledge page with tag
  `kaop-lab`, which the incident workflow uses. Remediation and the investigators search it at the start of a run.

## 8. Rehearsal

Follow [runbook.md](runbook.md). After a rehearsal, close the PR without merging and wait for the alert to return
to Normal (about 15 minutes) before the next run.
