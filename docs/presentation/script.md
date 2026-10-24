# Talk track (40 minutes)

The deck's speaker notes carry the same lines. **SHOW** means it is on screen in the product, not described.

| Time | Slide | Goal |
|---|---|---|
| 0–3 | 1 Title | Discovery question; listen |
| 3–6 | 2 Problem | Name their pain in their words |
| 6–9 | 3 What KAOP is | Build, run, govern, optimize, with mechanisms |
| 9–12 | 4 Governance | Six layers; "a prompt is not a permission model" |
| 12–14 | 5 Visibility | Map their pain to screens |
| 14–16 | 6 Workflows | Two triggers, two owners, one control plane |
| 16–17 | 7 Boundaries | Who can do what, and what enforces it |
| 17–30 | 8 Live demo | Bad rollout → outage → alert → RCA → approval → PR → review |
| 30–33 | 9 Pilot | One owner, two weeks, agreed thresholds |
| 33–45 | Backups | Discussion, objections, how I built the pitch |

## 1. Open with a question

> "When a team in your org launches a new AI agent today, who decides what it can touch, and where would you
> look to see what it actually did?"

Pause. Listen for **inventory**, **access** or **audit**. Reuse their word for the rest of the session.

> "I'll use one real Kubernetes incident to show how KAOP answers that, then propose a two-week way to prove it
> in your environment."

## 2. The problem

> "Nobody plans agent sprawl. Support adds a troubleshooting bot, SRE wires an agent to observability, developers
> add one to pull requests. Each is sensible. The platform team inherits three questions: who owns it, what can it
> touch, what did it do?"

> "Gartner expects over 40% of agentic projects to be cancelled by 2027, and the reasons are governance, value and
> cost, not model quality."

Ask: *"Which of these three is costing your platform team the most today?"*

## 3. What KAOP is

> "KAOP is the platform you'd build for agents if you treated them like production services."

- **Build.** Catalog agents built from Komodor's Klaudia expertise, or import your own: LangChain, the Claude Agent SDK, ADK.
- **Run.** Alert endpoints, schedules and Slack start runs; workflows fan out to specialists; agents run in Komodor cloud or inside your network, outbound only.
- **Govern.** Identity, default-deny permissions, guardrails, approvals and audit are platform features, not prompt text.
- **Optimize.** Every run records inputs, tool calls, reasoning, output and cost; evaluations and budgets decide what scales.

## 4. Governance

> "If an agent can delete a deployment, a prompt telling it not to is not a control. KAOP governs an agent like a
> person, by the same machinery. It can't grant itself a capability by changing its own code."

Spend the time on **Permissions** and **Approvals**. Then the lab:

> "The Kubernetes RCA agent's only access is its Kubernetes ServiceAccount, bound to the built-in view role. I
> verified with `kubectl auth can-i` that it can't read Secrets, exec, or write. The GitHub Agent can open one PR,
> and its call waits for me. The Code Reviewer can comment but never approve."

Ask: *"Which actions in your environment should never happen without a person approving them?"*

## 5. Visibility

Map their pain:

- **Inventory** → Fleet health and Spend.
- **Access** → Access explorer.
- **Audit** → Runs & evidence and the Audit log.
- **Approvals** → the Attention inbox.

> "Each of these is a screen I'll open on the runs we're about to create."

## 6. Two workflows

> "Two workflows owned by two teams, which is exactly the sprawl you described, under one policy model."

> "Notice what's not here: no agent changes the running cluster. The fix goes through git, review and a human,
> the same path your engineers use."

## 7. Boundaries

> "This is the slide for your security team: what each agent can read, what it can change, and what enforces that
> outside the agent."

## 8. Live demo

Follow [../runbook.md](../runbook.md). Keep the terminal under two minutes of talk in total.

1. `./scripts/demo.sh preflight`: "Healthy, and carrying a latent defect from last week's rollout." **SHOW** the commit on GitHub.
2. `./scripts/demo.sh outage --approve-live-mutation`: "Redis just went away."
3. Terminal shows `restarts=+1 … CrashLoopBackOff`: "Readiness failing is right. Liveness failing is the bug."
4. **SHOW** Grafana: the rule goes Alerting, about 2 minutes in. "Detection is Grafana's job. Now KAOP."
5. **SHOW** the KAOP incident: both investigation runs, the conclusion, confidence, cited evidence and tool calls. Ask: *"Would this be enough for your on-call engineer to act?"*
6. **SHOW** Attention: approve the GitHub Agent's PR. "The agent proposed. I decided. That's on the run record."
7. **SHOW** GitHub: the PR plus the Code Reviewer's comment. "Separate trigger, separate identity. It comments, never merges."
8. Press Ctrl-C: Redis returns and the restart count is printed. "Kubernetes killed a healthy process N times for a Redis problem, and paged the API team."
9. If time allows: merge, `deploy --ref origin/main`, then a 90-second outage. Zero restarts.

**If KAOP is slow**, open the completed rehearsal incident and say it is the rehearsal.
**If the GitHub Agent is unavailable**, open the prepared PR.

## 9. Pilot close

> "One workflow, one owner, pass criteria we agree today. Week one: incident investigation on one cluster,
> read-only, approvals on every write. Week two: the Code Reviewer on one repo. Then we decide together."

> "I'm not putting a percentage on this slide. I'd rather measure your baseline and prove the delta."

Ask: *"Which workflow would you sponsor first, and who owns it?"* Then stop talking.

## Questions to expect

| Question | Answer |
|---|---|
| "We'll build this ourselves." | "You can build an agent. Building identity, approvals, audit, budgets and evaluation around every agent, for every team, is the platform." |
| "Komodor already has Klaudia. Why KAOP?" | "Klaudia is the expertise. KAOP is the operating model that runs it beside your own agents, under one policy and one record." |
| "What if the agent is wrong?" | "Remediation separates observation from inference and can say no action. Every write needs approval. Evaluations grade runs over time." |
| "How do you know it's the probe?" | "Same outage, both configurations: with liveness on `/readyz`, five kills in five minutes and the alert fires; with `/healthz`, zero restarts and the alert stays Normal." |
| "Why a PR instead of fixing it live?" | "Git is the source of truth. A live patch creates drift and skips review. KAOP can act live through Klaudia, but that's the wrong default for config." |
| "Why Grafana and not Komodor's own detection?" | "Customers already have alerting. KAOP meets them there: any alert source can post to an endpoint." |
| "What did the Code Reviewer need from the repo?" | "Only the GitHub App installation on this repo. There is no config file; it reviews against its own rubric." |
| "What does it cost?" | "Every run shows its cost. Budgets block new runs at a cap. The pilot measures cost per useful RCA." |
