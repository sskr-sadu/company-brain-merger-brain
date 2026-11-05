"""PR checks: map a pull request to the SOPs, policies, contracts and plan the brain holds.

Each check cites the rule it applied (the exact passage and its file). Every rule is looked up in the brain at
check time, among the items the PR's author is bound by (their team's rules and what is published down to
them), so changing a policy file changes the check. Any failure becomes a conflict on the board.
"""
import json
import re

from . import access, conflicts, db

P = db.ORG["people"]
SENSITIVE_PATHS = re.compile(r"(^|/)(identity|billing|auth|payments?)/", re.I)
TICKET = re.compile(r"\b[A-Z]+-\d+\b")


def _rule(author, pattern):
    """Find the governing rule passage among the items the author is bound by."""
    where, args = access.item_filter_sql(author)
    for it in db.q(f"SELECT i.* FROM items i WHERE {where} ORDER BY i.strength='hard' DESC, i.authority DESC", args):
        if re.search(pattern, re.sub(r"\s+", " ", it["text"]), re.I):
            return it
    return None


def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


def check(pr):
    a = pr["author"]
    team = P[a]["home"]
    results, affected = [], []

    def add(name, ok, rule, detail):
        results.append({"name": name, "ok": ok, "detail": detail,
                        "rule": _norm(rule["text"]) if rule else None, "file": rule["source_id"] if rule else None,
                        "scope": db.ORG["scopes"][rule["scope"]]["name"] if rule else None})

    # 1. Every change links to a ticket
    r = _rule(a, r"every change links to a (jira )?ticket")
    tk = pr.get("ticket") or (TICKET.search(pr["title"]).group(0) if TICKET.search(pr["title"]) else None)
    add("Linked to a ticket", bool(tk), r, f"Links {tk}." if tk else "No ticket linked in the title or the PR.")

    # 2. Ships through the release train unless it is a Sev1
    r = _rule(a, r"outside the release train unless|only sev1")
    on_train = pr["base"].startswith("release/") or "sev1" in [l.lower() for l in pr.get("labels", [])]
    add("Ships through the release train", on_train, r,
        f"Targets {pr['base']}." if on_train else f"Targets {pr['base']}, outside the release train, and is not labelled Sev1.")

    # 3. Identity or billing code needs a Security reviewer
    sensitive = [f for f in pr.get("files", []) if SENSITIVE_PATHS.search(f)]
    if sensitive:
        r = _rule(a, r"identity or billing code need a reviewer from security")
        ok = "security" in [x.lower() for x in pr.get("reviewers", [])]
        add("Security reviewer on sensitive code", ok, r,
            f"Touches {', '.join(sensitive)}; " + ("Security is a reviewer." if ok else "no Security reviewer requested."))

    # 4. Matches the plan: the ticket is planned work for the author's team, and the PR isn't off-plan
    plan_items = db.q("SELECT * FROM items WHERE scope=? AND status='current'", (team,))
    planned = {t for it in plan_items for t in TICKET.findall(it["text"])}
    off = db.q("SELECT * FROM tasks WHERE who=? AND off_plan IS NOT NULL", (a,))
    off_hit = next((t for t in off if t["title"].lower()[:18] in pr["title"].lower()), None)
    goal = next((it for it in plan_items if re.search(r"deliver|goal", it["text"], re.I)), None)
    if off_hit or not tk or tk not in planned:
        why = (f"This is “{off_hit['title']}”, which is not in the team plan ({off_hit['off_plan'].lower()})." if off_hit
               else f"{tk} is not in {db.ORG['scopes'][team]['name']}'s plan." if tk else "No planned ticket, so the work can't be matched to the plan.")
        add("Matches the team plan", False, goal, why)
    else:
        add("Matches the team plan", True, goal, f"{tk} is planned work for {db.ORG['scopes'][team]['name']}.")

    # 5. Breaking a shared API needs the consuming teams' contract terms
    breaking = "breaking-change" in pr.get("labels", []) or re.search(r"\b(removed|retire|breaking)\b", pr.get("body", ""), re.I)
    if breaking:
        for c in db.q("SELECT * FROM contracts WHERE provider=?", (team,)):
            if re.search(r"identity", c["title"], re.I) and any(re.search(r"identity/api", f) for f in pr.get("files", [])):
                ok = bool(pr.get("deprecation_notice"))
                r = {"text": "Must-have: " + c["must_have"], "source_id": c["source_id"], "scope": c["scope"]}
                add(f"Contract: {c['title']}", ok, r,
                    "Deprecation notice sent." if ok else f"Breaking change to an API {db.ORG['scopes'][c['consumer']]['name']} depends on, with no notice or compatibility period.")
                if not ok:
                    affected.append(c["consumer"])
        r = _rule(a, r"breaks its consumers needs a deprecation notice")
        if r and not pr.get("deprecation_notice"):
            add("Deprecation notice to consuming teams", False, r, "The PR removes behaviour other teams use without a deprecation notice.")
    return results, affected


def run(pr):
    results, affected = check(pr)
    failed = [r for r in results if not r["ok"]]
    a = pr["author"]
    team = P[a]["home"]
    cid = None
    if failed:
        lead = db.ORG["scopes"][team]["owner"]
        owners = [a] + ([lead] if lead != a else []) + [db.ORG["scopes"][x]["owner"] for x in affected]
        plan_fail = any(r["name"] == "Matches the team plan" for r in failed)
        title = (f"PR #{pr['number']} “{pr['title']}” " +
                 ("deviates from the plan and breaks team rules" if plan_fail and len(failed) > 1 else
                  "deviates from the plan" if plan_fail else
                  f"breaks {len(failed)} rule{'s' if len(failed) > 1 else ''}"))
        first = failed[0]
        c = {"id": f"pr-{pr['number']}", "kind": "pr", "trigger": "pr_checks", "scope": team, "title": title,
             "evidence": [[f"PR #{pr['number']} by {P[a]['name']}", pr["body"], f"{pr['repo']}: {pr['head']} → {pr['base']}"],
                          [f"{first['scope'] or 'Team'} rule", first["rule"] or first["detail"], first["file"] or "plan"]],
             "extra": " ".join(f"✗ {r['name']}: {r['detail']}" for r in failed),
             "route": f"Goes to {P[a]['name']}" + (f" and {P[lead]['name']}" if lead != a else "") + (
                 f", and to {', '.join(P[db.ORG['scopes'][x]['owner']]['name'] for x in affected)} because it affects their team." if affected else "."),
             "options": (["Retarget to the release train and add the ticket", "Add it to the plan (lead approves)", "Close the PR"]
                         if plan_fail else
                         ["Add a compatibility field and send the deprecation notice", "Get the consuming team's sign-off first", "Hold the PR for the next train"]),
             "visible_to": owners, "notify": owners, "origin": team, "affected": affected, "actor": a,
             "checks": results}
        conflicts.upsert(c, replace=True)
        cid = c["id"]
    db.x("INSERT OR REPLACE INTO prs VALUES (?,?,?,?,?,?,?,?)",
         (pr["number"], a, pr["title"], pr["base"], json.dumps(results), cid, json.dumps(affected), pr.get("created", access.TODAY)))
    db.audit("pr_checks", "checked", {"pr": pr["number"], "failed": [r["name"] for r in failed]}, access.TODAY)
    return {"number": pr["number"], "checks": results, "conflict": cid}


def from_github(payload):
    """Accept a GitHub `pull_request` webhook payload (plus optional changed-file list) and run the checks."""
    pr = payload["pull_request"]
    handles = {p.get("github"): pid for pid, p in P.items() if p.get("github")}
    return run({"number": pr["number"], "repo": payload.get("repository", {}).get("full_name", ""),
                "author": handles.get(pr["user"]["login"], pr["user"]["login"]), "title": pr["title"],
                "head": pr["head"]["ref"], "base": pr["base"]["ref"], "ticket": None,
                "reviewers": [r["login"] for r in pr.get("requested_reviewers", [])] +
                             [t["slug"] for t in pr.get("requested_teams", [])],
                "labels": [l["name"] for l in pr.get("labels", [])], "files": payload.get("files", []),
                "deprecation_notice": False, "body": pr.get("body") or "", "created": pr.get("created_at", "")[:16]})


def visible_prs(person):
    out = []
    for r in db.q("SELECT * FROM prs ORDER BY created DESC"):
        if conflicts.can_see(person, P[r["author"]]["home"], json.loads(r["affected"]), r["author"]):
            out.append({"number": r["number"], "author": r["author"], "title": r["title"], "base": r["base"],
                        "checks": json.loads(r["checks"]), "conflict": r["conflict_id"], "created": r["created"]})
    return out
