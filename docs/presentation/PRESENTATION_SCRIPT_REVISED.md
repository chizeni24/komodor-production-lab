# KAOP | Full customer presentation and live-demo script
**Role:** Product Engineer presenting to platform engineering stakeholders\
**Format:** 30-45-minute pitch and customer discussion; seven-slide deck with one integrated live demo\
**Primary incident:** Redis dependency outage amplified by a faulty API liveness probe\
**Realism rule:** The script is an intended talk track. Any screen cue referencing KAOP results must be verified after workspace access. Never pretend a placeholder is a real outcome.

**Evidence update, October 24:** Two live Kubernetes rehearsals each produced two API restarts and fresh liveness HTTP 503 events, followed by verified automatic recovery, with recovery snapshots about 195 seconds from run start. Later read-only Grafana history independently confirmed Pending at 06:35:40 UTC, Alerting at 06:36:40 and Normal at 06:51:40: one episode covered both runs. The replacement token, read-only MCP and full local/Grafana preflight now pass. Receiver is still `empty`; KAOP delivery, agent governance and reviewer results remain unverified. These results prove avoidable API restarts, not a multi-service cascading outage. See `docs/grafana-verification.md`.

**Final closure update:** Preparation/base/head are published; the fresh PR is still unopened. Twenty-one local tests
and the probe guard passed again on preparation code `52c3a28`. The existing Actions workflow is configured but has
no observed remote run. Fresh read-only preflight at 14:25 UTC passed; at 14:26 Grafana was Normal/healthy with
query A=0 and receiver `empty`. These are timestamped snapshots, not KAOP outcomes. Use `docs/OPERATOR_CARD.md`
as the single command card and `docs/prelogin-status.md` as the acceptance/evidence index.

## Before the call: readiness checks, completed before the audience joins

Open five surfaces in order: (1) seven-slide deck; (2) terminal in `~/komodor-demo`; (3) Grafana Cloud alert rule and Explore; (4) KAOP incident workflow and agent permissions; (5) GitHub PR page and KAOP reviewer run. Increase terminal font. Hide passwords/tokens. Turn off distracting notifications. Run `./scripts/demo.sh preflight --grafana-proof artifacts/grafana-verification.json` after live rehearsal. `./scripts/smoke-test.sh` checks Kubernetes only and does not certify the external workflows. Confirm API and Redis Ready, `/healthz=200`, `/readyz=200`, `/leak=404`, Grafana recent telemetry, and the reviewer workflow listening. Keep `./scripts/demo.sh reset --approve-live-mutation` available; live use requires explicit authorization. Have previous real incident run evidence as a clearly identified fallback.

## Slide 1 | AI agents move fast. Can you govern them? (about 2 minutes)

**Say:**

"When a team launches a new AI agent today, who approves what it can access, and where can your platform team reconstruct what it actually did?"

**Pause for the customer's answer.**

**Use the answer:** Emphasize run/owner visibility if they describe inventory gaps, effective permissions if they describe access risk, or evidence and time to a useful decision if they describe investigation overhead. Carry that emphasis into the live workflow.

"The challenge isn't convincing engineers to use agents. They've already found the value. The challenge is scaling that value without handing every team a different set of credentials, permissions, policies, and logging conventions. That's where an agent platform stops being an experiment and becomes part of how engineering operates."

"Today I’ll use one Kubernetes failure to answer your question: can we reach a useful, evidence-backed decision while keeping action authority explicit? I’ll show the incident and the separately triggered PR review, then map the results to the visibility and controls your team needs. Before access and rehearsal are complete, this is our demo plan, not a claim that these integrations have run."

**Transition:** "First, let's look at what goes wrong when agents grow faster than the operating model around them."

## Slide 2 | Your next incident will cross agent boundaries (about 2 minutes)

**Say:**

"In most engineering organizations, agent adoption doesn't happen through one centrally planned rollout. A support team starts with a troubleshooting agent. SRE connects an agent to observability. Developers wire one into pull requests. Individually, those are sensible decisions. But the risks sit between them."

"Now the platform team has three questions to answer. Which agents are active and who owns them? What systems can each one read or change? And when something goes wrong, can we reconstruct the sequence from alert to investigation to code review?"

"When each team assembles its own workflow, proving the answer can mean collecting evidence across tools and owners. Is that something your platform team encounters today? As adoption grows, the opportunity is to make those answers repeatable."

**Ask:** "Of those three, is visibility, access control, or the lack of an end-to-end audit trail the bigger issue in your environment?"

**Bridge:** "KAOP's value starts with putting a common operating structure around agents, not asking every team to throw away what they've built."

## Slide 3 | One operating model for your agents (about 2 minutes)

**Say:**

"I think about KAOP in four responsibilities: build, run, govern, and optimize."

"Komodor already brings Kubernetes investigation expertise. We're planning to use KAOP's marketplace Kubernetes RCA agent and show how we invoke it, scope its authority, inspect its context, record its evidence and measure its usefulness alongside other workflows."

"Build means teams can start with ready-to-run agents or bring the workflows, tools, and agents they already use. Run means those capabilities don't live as isolated scripts. They can be connected to operational triggers and workflows. Govern means access, tool usage, policy and human decision boundaries are explicit. Optimize means you can assess whether the agents are actually producing useful outcomes, at an acceptable reliability and cost."

"For your platform team, the value is a reusable way to onboard the next agent: shared context, integrations, identity, controls, evaluation and run history. We can assess that operating model using the workflows you already care about."

"Shared context gives agents a consistent picture of services and dependencies; evaluations and per-run cost let us judge whether those workflows earn broader adoption. Those are platform capabilities we will distinguish from the specific results this lab proves."

**Stay credible:** These are Komodor's public product capabilities. The live lab later proves only the particular integrations and controls that have actually been configured.

**Transition:** "But there's an important distinction between telling an agent what it shouldn't do and actually preventing it."

## Slide 4 | Trust is enforced at the action boundary (about 3 minutes)

**Say:**

"A prompt that says 'be careful' isn't a security boundary. If an agent has permission to delete workloads, the fact that its instructions say not to is not enough."

"For this demonstration, I want the incident investigator to be able to read the Kubernetes namespace, inspect pod state, events and logs, and make a recommendation. I don't want that same identity to redeploy a workload, delete a pod, or change a Secret. Those are different risk classes."

"The GitHub reviewer has a separate role. It needs to read a diff and publish review feedback. That does not automatically grant it permission to merge a pull request or ship to production."

"KAOP's governance proposition is to make those boundaries visible, enforceable and reviewable. At the infrastructure level, Kubernetes RBAC also matters. If I claim read-only, I need to be able to show the actual scope of the identity and tools, not just an attractive workflow diagram."

**Live screen cue, only after access:** Show the actual installed agent permissions, approved tools, policies, and any human-approval gate configured. Do **not** say an approval was enforced if you haven't shown one. If only read-only access is implemented, say precisely that.

**Safe control proof:** Use the investigator's actual identity and a read-only authorization check or supported non-mutating policy test. Do not attempt a real delete/deploy to manufacture a denial. The presenter's operator kubeconfig is not evidence of the agent's effective permissions.

**Ask:** "Which actions in your environment should never happen without a person approving them?"

**Transition:** "Let's make this concrete with two separate workflows under one governance model."

## Slide 5 | One incident. Two workflows. One control plane. (about 2 minutes)

**Say:**

"There are two triggers in this story, and it's important not to conflate them."

"First, Grafana watches the application. When the restart alert fires, it should launch a KAOP incident investigation. That agent follows the evidence, works out why the service restarted, and returns a root cause, confidence and proposed fix."

"Second, GitHub emits a separate event when a developer opens a new pull request. KAOP's review workflow inspects the change and posts feedback. I'm not going to pretend the investigator automatically writes or merges code. That's a more ambitious orchestration we could design later. Today we're proving governed investigation and governed review as two distinct operational workflows."

"And that distinction is valuable. We can measure and control each boundary independently."

**Transition:** "Now I'll stop talking about capabilities and show you the failure itself."

## Slide 6 | Live: One fault. Follow every decision. (allow 10-15 minutes)

**Before switching screens say:**

"Here's our application. It's intentionally simple: a Python API talks to Redis inside Kubernetes. The point isn't that this is a sophisticated service. The point is that the failure hides in the relationship between the application, its dependency, and its health checks."

### Demo scene A | Establish the healthy state (about 1 minute)

**Action:** Terminal. Execute `./scripts/demo.sh preflight --grafana-proof artifacts/grafana-verification.json`. If it doesn't exist or hasn't passed acceptance tests, use the documented safe manual health-check commands rather than pretending the script exists.

**Current preparation state:** The scripts exist and two local fault/reset rehearsals passed. Full preflight correctly fails without current Grafana verification. `./scripts/smoke-test.sh` checks Kubernetes only and is not a substitute for complete live-demo readiness.

**Say:** "Both workloads are healthy. The API can reach Redis. Its readiness probe tests whether it can serve requests, and its liveness probe tests whether the process is alive. Those sound similar, but they answer different operational questions."

**If asked:** "Readiness can take an instance out of rotation; liveness can kill and restart it. You don't want an external Redis outage to decide whether a healthy API process should survive."

### Demo scene B | Show the control boundary (about 1 minute)

**Action:** KAOP agent policy/tool scope. Show actual controls if configured.

**Say:** "Before we run anything, here's the authority we've given the investigator. It can see the evidence it needs, but the decision to change infrastructure isn't silently delegated. That's the separation we want to preserve across teams and agents."

**If not configured:** Say "The lab's desired scope is read-only; I won't call it enforced until I can show the policy and Kubernetes permissions." Move on without faking controls.

### Demo scene C | Reproduce the failure (about 2-4 minutes, dependent on real alert timing)

**Action:** Terminal. Execute `./scripts/demo.sh trigger-liveness --approve-live-mutation --grafana-proof artifacts/grafana-verification.json --max-seconds 300` only after explicit consent and rehearsals. Choose the bound from the actual alert settings; 300 seconds is provisional. The runner holds in the foreground and automatically attempts restoration. Ctrl-C requests earlier recovery. Watch actual pod restarts/events, with an automatic bounded recovery plan.

**Timing gate:** The two measured local runs used 180-second budgets. They establish Kubernetes repeatability, not enough hold time for Grafana evaluation plus KAOP ingestion/investigation. Measure that path after access; confirm evidence was consumed before the approved recovery deadline. If it was not, recover safely and label the end-to-end test incomplete.

**Say:** "I'm changing one configuration: liveness now points to `/readyz`. That endpoint depends on Redis. I'll temporarily take Redis out of service. Our current code keeps the process and `/healthz` endpoint alive when Redis is unavailable; that startup-resilience fix is separate from this probe defect. Readiness becomes 503. Because we wired liveness to readiness, Kubernetes interprets that dependency failure as a dead process and restarts the API."

**Wait for real observed signals, narrate only actual ones.**

"Notice the difference between the trigger and the root cause. Redis going unavailable is the trigger. The unnecessary API restarts are caused by the probe configuration. Restarting the process harder won't solve that design mistake."

### Demo scene D | Show actual Grafana detection (about 1-2 minutes)

**Action:** Grafana Alert Rules, instance history and Explore. Only after the alert really enters Alerting should you say it fired. Confirm latest metric and relevant 503 events.

**Say:** "Grafana can tell us the API restarted. That signal alone doesn't establish why, whether the investigation is evidence-backed, or what the investigator is authorized to change. That's what I want to show in KAOP."

**If delayed:** "We're waiting for the alert's configured evaluation interval and pending period. While that runs, here's the Kubernetes event showing the failing liveness probe." Do not promise a time.

### Demo scene E | Show real KAOP investigation (about 2-3 minutes)

**Action:** KAOP workspace: incident notification, triggered run, evidence references, verdict, confidence, suggested remediation, tools invoked and policy log. Only if the workflow actually ran.

**Say, once verified:** "The key point is that the agent didn't just repeat a log line. It correlated the failed Redis dependency, the 503 readiness checks, the liveness configuration, and the restart history. The actionable conclusion is to keep Redis-sensitive readiness separate from process liveness. It also tells us what evidence supports that conclusion and how confident the agent is."

"Here are the tools and results recorded for this run. With the configured identity and policy visible, we can evaluate whether it stayed inside its permitted scope. A statement in the prompt alone would not prove that boundary."

**If access or delivery is missing:** State exactly what is missing and show authenticated Grafana/Kubernetes evidence only. Do not claim KAOP performed an investigation.

### Demo scene F | GitHub review of the actual remediation PR (about 2-3 minutes)

**Action:** After KAOP GitHub review workflow is active, open the PREPARED FRESH PR and show the real reviewer comment on the diff, plus the matching KAOP run. The committed default manifest already has `/healthz`; the PR must contain a genuine correction of a versioned faulty configuration.

**Disclose the actual base:** "This demo branch versions the faulty configuration we reproduced. The default branch already has `/healthz`; this PR makes a real correction against the disclosed faulty base." If the reviewer supports only the default base, use and describe the genuine regression-guard PR instead. Do not use this line until actual branches and a fresh non-empty PR exist.

**Say, once verified:** "Now the code-review workflow has a separate trigger. A PR opens, and the reviewer evaluates the change against the configured standards. We're not using the incident workflow as an excuse to bypass source control. We're keeping review, ownership and any eventual approval in the normal engineering path."

"GitHub Actions checks the deterministic parts: endpoint behavior, probe configuration and source consistency. The KAOP Reviewer separately analyzes the change and publishes feedback. The tests and the agent review give us different evidence for a human decision."

**CI truth gate:** The existing workflow has no observed remote run yet. Show its actual status at presentation time;
do not say Actions passed because 21 local tests passed. A failed guard on the deliberately faulty base is expected;
the corrected head should pass. Required merge checks/branch protection are not demonstrated by a workflow file.

"This is why I like this demonstration: the incident and the review have different triggers, but one consistent expectation around access, traceability and human accountability."

### Demo scene G | Reset and close the loop (about 1 minute)

**Action:** If the foreground runner has already restored the app, show its recovery result. Otherwise interrupt it and execute `./scripts/demo.sh reset --approve-live-mutation`; verify service Ready, probe `/healthz`, Redis up, `LEAK_ENABLED=false`. Show KAOP run history if available.

**Say:** "The application is healthy again. The restart alert may remain active until its evaluation window clears; I’ll show those as separate states. Once both workflows are verified, we have evidence of the failure, diagnosis, review and recorded decisions. That is the operating standard we can evaluate for your team."

**Bridge:** "So the question becomes: how would you roll this out responsibly in your environment?"

## Slide 7 | Start with one owner and a measurable pilot (about 2-3 minutes)

**Say:**

"I wouldn't ask a platform team to roll out hundreds of agents on day one. I'd start with one workflow where there's measurable pain, agreed boundaries, and a clear owner. Incident investigation is a good first candidate because evidence quality, investigation time, and escalation are easy to evaluate."

"Then I'd add a second workflow, like PR review. For each one, I'd define three things before scaling: the outcome we want, the action authority we're willing to grant, and how we'll know it worked."

"The success measures are practical: did the RCA reference real evidence; was the proposed fix actionable; did the reviewer comment on the correct PR and commit; were permission boundaries respected; and how much time and cost did it take? I don't need to invent a 40 percent improvement on a slide. I'd rather establish the baseline with you and prove the delta."

**Close with a decision question:**

"I would start with one owned workflow, explicitly scoped access, and a two-week scorecard. We would baseline evidence quality, time to a useful decision, policy adherence and cost per run, then agree whether the results justify expansion. Which workflow would you sponsor, and who should own the pilot?"

**Stop and let the customer respond.**

## Likely customer questions and strong, concise answers

**Doesn't Komodor already do root-cause analysis?**
"Yes. Komodor introduced KlaudiaAI for Kubernetes investigation in 2024. This demonstration uses that foundation to evaluate a broader operating model: a real alert starts an accountable investigation, and a separate PR starts a governed review. Our plan uses the marketplace Kubernetes RCA agent; we're not building a custom investigator."

**Presenter source boundary:** Komodor's September 18, 2024 KlaudiaAI announcement and September 16, 2026 KAOP announcement support this positioning. They do not establish exact agent branding, topology or configured tenant controls; verify those after login.

**Why do we need KAOP if we already use Grafana?**\
"Grafana detects and records a signal. The extra value we're evaluating is a controlled investigation that correlates data, explains root cause with evidence, and gives us a consistent policy and run record. We should measure whether that improves time to a useful decision, not just count alerts."

**Why not just put an AI coding agent on the cluster?**\
"A coding agent can be excellent at reasoning. My concern as a platform engineer is authority and accountability. Who can invoke it? Which tools and credentials does it get? What needs approval? What's recorded? KAOP's proposition is a common control layer around that capability."

**Could the incident investigator make the change automatically?**\
"Potentially, with deliberately designed permissions and approval gates, but I'm not assuming it in this demo. The first step is evidence-backed recommendations and human-reviewed PRs. We'd graduate specific actions only after proving safety and reliability."

**How do you know it's actually the liveness probe?**\
"The evidence to show is the fresh liveness HTTP 503 event, the configured `/readyz` path and a restart delta on the same pod UID after Redis is removed. The strongest control is to repeat the dependency outage with `/healthz` liveness and observe readiness failure without API restarts. I’ll call that control verified only after an approved run; unit tests already check the endpoint semantics."

**What enforces read-only?**\
"I want two independent protections: the real Kubernetes identity and RBAC governing the cluster calls, and the platform's per-agent tool/policy configuration. I can show you what is actually configured, and I won't equate a prompt instruction with permission enforcement."

**What if the agent is wrong?**\
"We separate what it observed from what it inferred. Require citations to underlying events or logs and an explicit confidence statement; keep higher-risk write actions behind review or approval; measure error rates over repeated runs before increasing autonomy."

**Is the GitHub reviewer automatically triggered by the incident?**\
"No, not in this scope. Grafana triggers the investigator. A fresh PR triggers the reviewer. The shared platform governs both. That distinction lets us understand each workflow's responsibility and authority."

**What is the business case?**\
"Reduce time spent assembling evidence, increase consistency of decisions, and let the platform team govern agent use without blocking every team. We'd baseline time to useful RCA, review quality, policy adherence, and cost, then scale only if those measures improve."

## Honest fallbacks

- If Grafana is delayed, show current Kubernetes probe failures while waiting. Don't mark delivery complete until the alert and KAOP run appear.
- If the laptop loses the cluster, don't perform an unplanned rebuild in front of the customer. Use a **previously recorded authentic run**, label it accurately, and explain what was previously tested versus not currently live.
- If KAOP isn't accessible, don't invent a reviewer comment or RCA. State the integration constraint and show the already verified local investigation evidence.
- If a PR is not reviewed automatically, keep it open; inspect webhook/repo permissions after the meeting. A manual or fake review does not satisfy the assignment.
- The memory-OOM experiment is backup evidence for technical Q&A, not a second live incident.

## Speaking and facilitation guardrails

- First person, customer-oriented, no long technical monologue and no jargon without a business reason.
- Pause for the customer. Invite pushback. Do not read the slide bullet by bullet.
- Keep the main demo on one connected story and two distinct triggers.
- Never use an invented ROI number, fabricated log, or pretend screenshot.
- Do not promise 10-12 minutes unless the actual automation and KAOP paths were timed in rehearsal.

**Suggested timing:** 3 minutes customer discovery; 7-9 minutes slides 2-5; 12-15 minutes real demo; 3 minutes close and adoption; 8-12 minutes discussion. Adapt to the interviewer's schedule and the live system's actual behavior.

**Offline desk walkthrough completed:** Commands, screen transitions, trigger separation, recovery and objection answers
have been checked against the code and original assignment. Spoken-script word count gives a preparation estimate only;
it excludes customer responses, live waits and discussion. No actual timed spoken rehearsal is claimed. Practice the
first-person discovery → evidence → authority → separate review → pilot transitions aloud, keep terminal explanation
under two minutes, and time the full 30–45 minute discussion after real KAOP integration is available.

## Product claim boundaries and sources

Slide 3 describes public product capabilities, not configured tenant outcomes. Slide 4 remains a proposed demo policy until actual RBAC/tool policy is shown. Slide 5 is a target workflow diagram. Slide 6 labels the supplied past-run result as historical. No benchmark or enforcement result is inferred from the public website.

## Sources

The four-page user-provided assignment (`Product Engineer Home Assignment(1).pdf`); the user's October 24 deep-dive brief; actual Kubernetes evidence in `docs/rehearsal-results.md`; supplied historical Grafana observations; and official Komodor materials at https://komodor.com/platform/, https://komodor.com/platform/govern-agents/, https://komodor.com/platform/run-agents/ and https://komodor.com/platform/optimize-agents/. Kubernetes probe semantics: https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/. Product capability claims are separate from observed tenant behavior. KAOP implementation instructions are to be verified at https://kaop.komodor.com/docs after access.
