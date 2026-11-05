# Northgate Brain: backend

A company brain for one organization (Northgate), served with its own UI. Standard-library Python only:
no installs needed.

## Run

```bash
cd merger-brain
python3 backend/server.py          # ingests data/northgate, runs the triggers, serves http://localhost:8000
python3 -m unittest discover -s backend/tests -v    # 22 demo-gate tests
```

Optional environment variables:

| Variable | Effect |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude writes the answers from the permitted passages (default model `claude-sonnet-5-5`, override with `BRAIN_MODEL`). Without it, answers are quoted extractively. Responses are cached in `backend/cache/`. |
| `GITHUB_REPO`, `GITHUB_TOKEN` | Approving a team or contract conflict creates a real GitHub issue in `owner/repo`. |
| `TRIGGERWARE_URL` | Triggerware server, default `localhost:5221`. Used when the `triggerware` package is installed. |

## What it does

| Piece | File | Notes |
| --- | --- | --- |
| Ingest | `brain/ingest.py` | Front-matter, redaction, injection quarantine, typed items with exact source spans, contracts |
| Access | `brain/access.py` | Top-down: own area and below, published-down items, contracts, live grants; restricted needs the CEO or the owning department head; drafts private |
| Ask | `brain/ask.py` | Permission filter in SQL before search; "blocked" with approvers when the answer is outside your area; cited answer, graph, access note |
| Conflicts | `brain/conflicts.py` | Member drift from a team rule, sibling-team clashes, contract breaches |
| Triggers | `brain/triggers.py` | `drift_findings`, `clashes`, `contract_breaches` as SQL with row deltas; Triggerware bridge |
| Plans | `brain/plans.py` | Three resolution plans per conflict: steps with owners and dates, effects on contracts and deadlines, effort; one recommended; choosing one adds or moves tasks |
| Who's on it | `brain/watchers.py` | Scans Slack and email for people discussing the conflict; handling, noticed, or nobody (with a nudge); quotes only from channels the viewer may read |
| Actions | `brain/actions.py` | Decision written back into the brain as a new source; GitHub issue |
| Plan | `brain/planner.py` | Day moves checked for capacity, critical path and dependencies; load balancing |
| Status | `brain/status.py` | Today, last 7 days, timeline, bottlenecks for one unit |
| Audit | `brain/db.py` | Hash-chained log; `GET /api/health` verifies the chain |

## Demo flow

1. Signed in as Tom: ask "Why are payment retries capped at 5?" → blocked, Request access.
2. Switch to Marcus Lee → Governance → Grant. Back to Tom → ask again → answered, marked as read under a grant.
3. Tom → Conflicts: the private release-train warning.
4. Wei or Priya → Conflicts: Platform's UUID decision breaks Billing → pick an option → the decision is saved
   into the brain; ask "What did we decide about the Identity API user id format?" and it is cited.
5. Click "Simulate: SSO moved to Q2" in the rail → Marcus or Elena → Conflicts: the Sales contract breach.
6. Work → the timeline status bar, what finished today / this week / last week (with summaries), and plans for tomorrow, the rest of this week and next week; move a task or Balance load.
7. "Reset demo data" restores everything.

## Triggerware

`brain/triggers.py` runs the three triggers locally after every ingest and decision, so the demo works
without a server. With the SDK installed and a server running, `TriggerwareBridge.register()` connects and
creates the same triggers. The SDK README does not document how a Triggerware table is backed by external data,
so the triggers need a Triggerware table named `conflicts` that reads `backend/brain.db`; ask the organizers for
their table example and add it in `register()`.

## API

`GET /api/org` · `POST /api/ask` · `GET /api/status?person&scope` · `GET /api/conflicts?person` ·
`POST /api/conflicts/{id}/resolve` · `POST /api/conflicts/{id}/nudge` · `POST /api/tasks/{id}/move` · `POST /api/tasks/balance` ·
`GET /api/governance?person` · `POST /api/requests` · `POST /api/requests/{id}/grant|deny` ·
`POST /api/grants/{id}/revoke` · `POST /api/demo/event` · `GET /api/health` · `POST /api/reset`


## Pull request checks

`POST /api/prs` takes a GitHub `pull_request` webhook payload (add a `files` list of changed paths) or `{"demo": 4431|4432|4433}`.
Each PR is checked against rules the brain holds, and every check cites its rule passage and file:

| Check | Rule source |
|---|---|
| Linked to a ticket | Engineering SOP "Every change links to a Jira ticket" |
| Ships through the release train | Platform scope "Nothing ships outside the release train unless it is a Sev1 fix" |
| Security reviewer on sensitive code | Engineering charter, for identity/billing/auth/payments paths |
| Matches the team plan | The ticket must be planned work in the author's team scope and not an off-plan task |
| Contract: <name> | Breaking changes to an API another team consumes need the contract's notice and compatibility period |

Any failure becomes a `pr` conflict (trigger `pr_checks`) with three resolution plans. `GET /api/prs?person=` lists checked PRs the viewer may see.

## Who sees which conflict

The board shows conflicts at your level, below you, and from other teams when they affect yours; never conflicts above you.
A member sees their own work (and private drift findings only they can see). A lead sees their own work, their teammates' work,
and another team's work whose `affected` list includes their team. A department head sees everything in the department;
the CEO sees everything. Each card says why it is shown: "your own work", "your area", or "another team's work that affects you".

Demo: in the rail, click PR #4431 (Tom's off-plan hotfix: fails ticket, release train, plan), #4432 (passes), #4433 (Wei's
Identity v2 change: breaks the Billing contract). Switch between Tom, Wei and Priya to see the visibility rule.

Tests: `python3 -m unittest discover -s backend/tests` (26 tests).

## Work tab

`GET /api/status?person=&scope=` returns, besides the milestones and blockers, a `work` block:
`done.today`, `done.week` (Monday to yesterday), `done.past` (last Monday to Sunday) with a `summary` for each,
and `plan.today/tomorrow/week/next` task ids. Finished work comes from `completed` in `_plan.json` (what the brain read
from git, tickets, Slack, email and CRM) plus decisions settled in the brain; it follows the same access rule as tasks.

## Merger brain (Northgate acquires Pulsepoint)

Switch the sidebar from **Northgate** to **Northgate × Pulsepoint**. Same layout as the company brain: an explorer tree of both companies (each unit shows its partner, e.g. Platform ↔ Core; click to focus), tabs Ask · Work · Teams · Conflicts · Plan · Fusion (Ask: `POST /api/merger/ask` searches only your own company's integration work for your area plus the other company's files at the level your phase and grants allow; a named unit you can't read deeply returns what is open plus who can grant more), and **Cross-company access** at the bottom (requests waiting for you, ask for access, active grants with revoke, and what you can see in the other company by phase). Only cross-company content is shown, and it is enforced per viewer: your own company's integration work for your area (members and leads see their pair, heads their department, the integration office and CEO everything); the other company only at the level the current phase and your grants allow (published rules, team card, pair space, team area). Files you can't read show as locked with a pointer to Cross-company access; before close only the clean team sees anything. The merger brain reads both company brains plus a deal layer (`data/deal/merger.json`,
`backend/brain/merger.py`) and never edits the company brains.

| Tab | What it shows |
|---|---|
| Overview | Deal, the five phases (Before close, Q1 Stabilize, Q2 Align, Q3 Integrate, Q4 Fuse), the gate check for the current phase, the Day-0 clash register (11 clashes, each quoting both companies' files; pricing never quoted), 5 look-alike rules checked and not flagged, synergies, shared customers matched by domain |
| Plan | 2–3 options per stage with the chosen one, the current plan version with task state, and what changed from the last version |
| Teams | Five team pairs (Platform↔Core, Billing↔Billing, Engineering↔Engineering, Enterprise↔Mid-market, People↔People): mode, contract, rituals, culture bridge, and Q1–Q4 goals, joint tasks with an owner from each company, and done-when measures. Pulsepoint Integrations is unpaired and mirrors Platform for access |
| Conflicts | Events in either brain checked against plan tasks (trigger `plan_task_conflicts`). Negotiation chain: task owners → department heads → integration lead → sponsor. Choosing a resolution writes the next plan version (`data/deal/plan-vN.md`) |
| Access | Per person: each unit of the other company × phase. Rule: mirror position (what the matching job could see) ∩ phase cap; owning side approves; restricted data and drafts never cross before fusion |
| Fusion | Unit-by-unit fusion when checks pass (phase, no open conflicts, clashes decided, customers linked). New `fz:` id, old ids kept as aliases, every item tagged with its company, access recalculated, fusion record in the audit log |

Ids are prefixed by company (`ng:`, `pp:`, fused `fz:`). Demo: Merger → "Simulate: Pulsepoint keeps daily deploys" →
choose the recommended plan → Plan tab shows v2 → move to Q3 → Fusion → fuse Billing.

API: `GET /api/merger`, `POST /api/merger/phase`, `POST /api/merger/event`, `POST /api/merger/conflicts/{id}/resolve`,
`POST /api/merger/fuse/{pair}`, `GET /api/merger/access?person=&unit=&kind=&phase=`, `POST /api/merger/reset`, `POST /api/merger/requests`, `POST /api/merger/requests/{id}/grant|deny|revoke`.

Triggerware: the merger triggers (`plan_task_conflicts`, `gate_readiness`, `unit_fusion_ready`) register through the same
bridge as the company triggers. Cards say "local trigger engine" unless the bridge reports a live Triggerware connection.

Tests: `python3 -m unittest discover -s backend/tests` (37 tests: 26 company brain, 11 merger).

## Triggerware

The brain's reminders are Triggerware triggers. `backend/brain/triggers.py` uses the tw2-sdks Python client (included in `tw2-sdks/python`):
1. `tables.create(prompt=...)` makes a Triggerware table `brain_conflicts` whose rows come from `GET /api/triggerware/conflicts` (every company and merger conflict: id, kind, status, title, scope, created).
2. `triggers.create(name, description, sql, schedule)` registers `drift_findings`, `clashes`, `contract_breaches`, `pr_checks` and `plan_task_conflicts` as SQL over that table.
3. `triggers.watch` streams each delta back; added rows become notifications in the brain.

Run it: `pip install ./tw2-sdks/python`, start the Triggerware server, then `TRIGGERWARE_URL=localhost:5221 BRAIN_URL=http://localhost:8000 python3 backend/server.py`.
`/api/health` and the sidebar report the connection. Without a server the local engine fires the same triggers with the same added/removed delta semantics, and conflict cards say which one fired.
