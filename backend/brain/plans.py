"""Resolution plans: each option on a conflict becomes a concrete plan with steps, owners, dates, effects on
contracts and deadlines, effort, and the task changes applied when it is chosen. One plan is recommended:
the one that keeps every contract must-have and costs the least."""
import json

from . import access, db

P = db.ORG["people"]


def _ms(label_like):
    r = db.q("SELECT * FROM milestones WHERE label LIKE ?", (f"%{label_like}%",))
    return r[0] if r else None


def _n(pid):
    return P[pid]["name"]


def team_clash(c):
    vis = json.loads(c["visible_to"])
    lead_a, lead_b, sup = vis[0], vis[1], vis[2]
    saml = _ms("SAML")
    saml_txt = f"SAML login is already {saml['state'].lower()} ({saml['progress']}% done, due {saml['date']})" if saml else ""
    return [
        {"option": c_opts(c)[0], "recommended": True,
         "summary": "Ship UUIDs next to the integer IDs for one release train, then retire the integers once Billing has moved.",
         "steps": [{"what": "Identity v2 returns both user_id (integer) and user_uuid", "owner": lead_a, "due": "2027-02-17"},
                   {"what": "Announce the deprecation to every consuming team, one train ahead", "owner": sup, "due": "2026-11-13"},
                   {"what": "Billing switches its invoice job and tables to user_uuid", "owner": lead_b, "due": "2027-05-15"},
                   {"what": "Retire the integer IDs in the Q2 train", "owner": lead_a, "due": "2027-06-15"}],
         "effects": [{"ok": True, "text": "Keeps the Engineering contract: one train of notice and one of compatibility."},
                     {"ok": True, "text": "SSO and SCIM keep the Q1 date; nothing moves for Sales."},
                     {"ok": False, "text": "Platform carries both ID formats for one train (about 3 extra days of work)."}],
         "effort": "About 3 days for Platform, 6 weeks for Billing spread over Q1 and Q2",
         "task_changes": [{"add": {"who": lead_a, "title": "Identity v2: add user_uuid alongside user_id", "hours": 3, "day": "2026-11-05", "priority": 1}},
                          {"add": {"who": sup, "title": "Announce Identity v2 deprecation to consuming teams", "hours": 1, "day": "2026-11-06", "priority": 2}}]},
        {"option": c_opts(c)[1], "recommended": False,
         "summary": "Billing migrates inside the Q1 train, with a Platform engineer helping full time.",
         "steps": [{"what": "Finish the migration estimate", "owner": lead_b, "due": "2026-11-05"},
                   {"what": "Lend one Platform engineer to Billing for 6 weeks", "owner": lead_a, "due": "2026-11-09"},
                   {"what": "Migrate invoices and payment methods to UUIDs, with a Finance reconciliation sign-off", "owner": lead_b, "due": "2027-02-17"}],
         "effects": [{"ok": True, "text": "Integer IDs can be retired in Q1 as Platform planned."},
                     {"ok": False, "text": f"Takes an engineer off Platform for 6 weeks while {saml_txt}." if saml_txt else "Takes an engineer off Platform for 6 weeks."},
                     {"ok": False, "text": "Puts the Sales SSO contract (live before 2027-03-31) at higher risk."}],
         "effort": "6 engineer-weeks inside Q1",
         "task_changes": [{"add": {"who": lead_a, "title": "Plan a 6-week loan of one engineer to Billing", "hours": 1, "day": "2026-11-05", "priority": 1}}]},
        {"option": c_opts(c)[2], "recommended": False,
         "summary": "Keep integer IDs through Q1 and switch everything in the Q2 train.",
         "steps": [{"what": "Move the UUID switch to the Q2 train", "owner": lead_a, "due": "2026-11-13"},
                   {"what": "Check whether SCIM can ship in Q1 without globally unique IDs", "owner": lead_a, "due": "2026-11-20"},
                   {"what": "Billing migrates during Q1 at its own pace", "owner": lead_b, "due": "2027-05-15"}],
         "effects": [{"ok": True, "text": "No rush for Billing."},
                     {"ok": False, "text": "SCIM needs globally unique IDs, so SCIM likely slips to Q2."},
                     {"ok": False, "text": "Sales gets SAML by March but not SCIM, which the Acme renewal may not accept."}],
         "effort": "Low now, but moves risk onto the Sales contract",
         "task_changes": []},
    ]


def contract_breach(c):
    po, co = json.loads(c["notify"])
    return [
        {"option": c_opts(c)[0], "recommended": True,
         "summary": "Ship SAML login for Acme by the must-have date and deliver SCIM provisioning in Q2.",
         "steps": [{"what": "Confirm with Acme Health that SAML-only meets the renewal condition", "owner": co, "due": "2026-11-06"},
                   {"what": "Keep PLAT-2210 (SAML) in the Q1 train; move PLAT-2214 (SCIM) to Q2", "owner": po, "due": "2026-11-09"},
                   {"what": "SAML live for Acme Health", "owner": po, "due": "2027-03-15"}],
         "effects": [{"ok": True, "text": "Meets the contract must-have: live before 2027-03-31."},
                     {"ok": True, "text": "Matches what Elena is already checking with Acme."},
                     {"ok": False, "text": "SCIM provisioning arrives one quarter later."}],
         "effort": "No extra people; SCIM work moves to Q2",
         "task_changes": [{"add": {"who": co, "title": "Confirm SAML-only meets Acme's renewal condition", "hours": 1, "day": "2026-11-06", "priority": 1}}]},
        {"option": c_opts(c)[1], "recommended": False,
         "summary": "Put one more engineer on SSO so the full scope still makes Q1.",
         "steps": [{"what": "Move Tom Okafor's off-plan export work to next week and put him back on PLAT-2210", "owner": "wei", "due": "2026-11-05"},
                   {"what": "Assign a named owner to SCIM (PLAT-2214)", "owner": "wei", "due": "2026-11-06"},
                   {"what": "Weekly SSO check-in with Sales until the freeze", "owner": po, "due": "2027-02-17"}],
         "effects": [{"ok": True, "text": "Full SSO, SAML and SCIM, in the Q1 train."},
                     {"ok": True, "text": "Also resolves Tom's off-plan work."},
                     {"ok": False, "text": "Little slack left before the 2027-02-17 freeze."}],
         "effort": "One engineer refocused, no new hires",
         "task_changes": [{"move": "T2", "to": "2026-11-09"},
                          {"add": {"who": "wei", "title": "Assign an owner to SCIM (PLAT-2214)", "hours": 1, "day": "2026-11-05", "priority": 1}}]},
        {"option": c_opts(c)[2], "recommended": False,
         "summary": "Ask Acme Health to move the SSO condition to Q2 in exchange for a renewal credit.",
         "steps": [{"what": "Propose a new SSO date and a credit to Acme's CIO", "owner": co, "due": "2026-11-13"},
                   {"what": "CFO approves the credit (discounts above 25% need the CFO)", "owner": "dana", "due": "2026-11-20"}],
         "effects": [{"ok": False, "text": "Changes a customer commitment; Acme may run a competitive evaluation."},
                     {"ok": False, "text": "Costs revenue on a $1.9M account."},
                     {"ok": True, "text": "Engineering keeps its Q2 plan unchanged."}],
         "effort": "Commercial negotiation; no engineering change",
         "task_changes": [{"add": {"who": co, "title": "Draft Acme Health new-date proposal", "hours": 2, "day": "2026-11-09", "priority": 1}}]},
    ]


def drift(c):
    me = json.loads(c["visible_to"])[0]
    return [
        {"option": c_opts(c)[0], "recommended": False,
         "summary": "Ship the export fix with the next release train, like any non-urgent change.",
         "steps": [{"what": "Open a ticket for the export fix in the Q1 train", "owner": me, "due": "2026-11-05"},
                   {"what": "Tell the prospect the fix ships with the Q1 release", "owner": "sam", "due": "2026-11-06"}],
         "effects": [{"ok": True, "text": "Follows the release-train rule."}, {"ok": False, "text": "PLAT-2210 is still stalled."}],
         "effort": "None now", "task_changes": [{"move": "T2", "to": "2026-11-09"}]},
        {"option": c_opts(c)[1], "recommended": False,
         "summary": "Treat it as urgent: write down why it is a Sev1 and get your lead to agree.",
         "steps": [{"what": "Write the Sev1 justification", "owner": me, "due": "2026-11-04"},
                   {"what": "Platform lead approves or rejects", "owner": "wei", "due": "2026-11-05"}],
         "effects": [{"ok": False, "text": "The bug is not a Sev1 by the team's own definition."},
                     {"ok": False, "text": "Your lead will see the plan once you ask."}],
         "effort": "1 hour", "task_changes": []},
        {"option": c_opts(c)[2], "recommended": True,
         "summary": "Do the SSO work first: SAML today, the export fix next week in the train.",
         "steps": [{"what": "Spend today on PLAT-2210, SAML login", "owner": me, "due": "2026-11-04"},
                   {"what": "Move the export fix to next week and file it for the Q1 train", "owner": me, "due": "2026-11-09"}],
         "effects": [{"ok": True, "text": "Unblocks the SSO contract Sales depends on."},
                     {"ok": True, "text": "Follows the release-train rule."},
                     {"ok": True, "text": "Brings today back under 6 hours."}],
         "effort": "No extra work; a reorder", "task_changes": [{"move": "T2", "to": "2026-11-09"}]},
    ]


def c_opts(c):
    return json.loads(c["options"])


def pr(c):
    a = c["actor"]
    lead = db.ORG["scopes"][c["origin"]]["owner"]
    opts = c_opts(c)
    aff = json.loads(c["affected"] or "[]")
    num = c["id"].split("-")[1]
    if "plan" in c["title"]:
        return [
            {"option": opts[0], "recommended": True,
             "summary": "Keep the change, but ship it the normal way: a ticket, and the next release train.",
             "steps": [{"what": f"Open a ticket for PR #{num} and link it", "owner": a, "due": "2026-11-05"},
                       {"what": "Retarget the PR to release/q1-2027", "owner": a, "due": "2026-11-05"},
                       {"what": "Return to the planned SSO work (PLAT-2210)", "owner": a, "due": "2026-11-05"}],
             "effects": [{"ok": True, "text": "Follows the ticket and release-train rules."},
                         {"ok": True, "text": "Planned SSO work keeps its time."},
                         {"ok": False, "text": "The prospect sees the fix with the Q1 release, not Friday."}],
             "effort": "15 minutes of PR housekeeping",
             "task_changes": [{"move": "T2", "to": "2026-11-09"}]},
            {"option": opts[1], "recommended": False,
             "summary": "The lead decides the work belongs in the plan and makes room for it.",
             "steps": [{"what": "Decide whether the export fix outranks SAML this week", "owner": lead, "due": "2026-11-05"},
                       {"what": "Add a ticket and a planned day for it", "owner": lead, "due": "2026-11-05"}],
             "effects": [{"ok": True, "text": "The work becomes visible and planned."},
                         {"ok": False, "text": "Takes time from SAML (PLAT-2210), which a Sales contract depends on."}],
             "effort": "A planning decision", "task_changes": []},
            {"option": opts[2], "recommended": False,
             "summary": "Drop the change for now.",
             "steps": [{"what": f"Close PR #{num} with a note to the prospect owner", "owner": a, "due": "2026-11-05"}],
             "effects": [{"ok": True, "text": "No rule broken."}, {"ok": False, "text": "The prospect's bug stays open."}],
             "effort": "None", "task_changes": []},
        ]
    cons = db.ORG["scopes"][aff[0]]["owner"] if aff else lead
    return [
        {"option": opts[0], "recommended": True,
         "summary": "Ship the new field alongside the old one and tell every consuming team, so nobody breaks.",
         "steps": [{"what": "Keep the integer user_id and add user_uuid next to it in the PR", "owner": a, "due": "2026-11-06"},
                   {"what": "Send the deprecation notice to consuming teams", "owner": a, "due": "2026-11-06"},
                   {"what": "Confirm the migration date with the consuming team", "owner": cons, "due": "2026-11-09"}],
         "effects": [{"ok": True, "text": "Keeps the Engineering contract with the consuming team."},
                     {"ok": True, "text": "The PR still makes the Q1 train."},
                     {"ok": False, "text": "About a day of extra work in the PR."}],
         "effort": "About 1 day",
         "task_changes": [{"add": {"who": a, "title": f"PR #{num}: add user_uuid alongside user_id, send deprecation notice", "hours": 3, "day": "2026-11-05", "priority": 1}}]},
        {"option": opts[1], "recommended": False,
         "summary": "Merge as is, once the consuming team signs off on the break.",
         "steps": [{"what": "Ask the consuming team to sign off", "owner": a, "due": "2026-11-05"},
                   {"what": "Consuming team migrates before the freeze", "owner": cons, "due": "2027-02-17"}],
         "effects": [{"ok": False, "text": "Billing must finish a 6-week migration inside Q1."},
                     {"ok": True, "text": "No extra work in the PR."}],
         "effort": "Moves the cost to the consuming team", "task_changes": []},
        {"option": opts[2], "recommended": False,
         "summary": "Hold the PR until the Q2 train.",
         "steps": [{"what": f"Hold PR #{num} and retarget it to the Q2 train", "owner": a, "due": "2026-11-06"}],
         "effects": [{"ok": True, "text": "No break this quarter."}, {"ok": False, "text": "SCIM, which needs the new IDs, likely slips."}],
         "effort": "None now", "task_changes": []},
    ]


BUILDERS = {"team_clash": team_clash, "contract_breach": contract_breach, "drift": drift, "pr": pr}


def plans_for(c):
    return BUILDERS.get(c["kind"], lambda _: [])(c)


def apply(c, option, person):
    plan = next((p for p in plans_for(c) if p["option"] == option), None)
    if not plan:
        return []
    done, n = [], db.q("SELECT count(*) n FROM tasks")[0]["n"]
    for ch in plan["task_changes"]:
        if "move" in ch:
            db.x("UPDATE tasks SET day=? WHERE id=?", (ch["to"], ch["move"]))
            done.append(f"Moved {ch['move']} to {ch['to']}")
        else:
            a = ch["add"]
            n += 1
            tid = f"R{n}"
            db.x("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (tid, a["who"], a["title"], a["hours"], a["day"], a["priority"], None, None, None, None))
            if a["who"] != person:
                db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
                     (a["who"], f"New task from the plan “{option}”: {a['title']} ({a['day']})", tid, access.TODAY))
            done.append(f"Added “{a['title']}” for {_n(a['who'])} on {a['day']}")
    return done
