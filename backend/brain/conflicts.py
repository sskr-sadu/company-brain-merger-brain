"""Conflict detectors. Each finds one kind of problem in the brain and writes it to the `conflicts` table,
which the triggers watch. Detectors are deterministic and explainable: every conflict carries the two
passages it rests on.

  drift            a member's draft breaks a hard rule of their team or department (scenario 1)
  team_clash       two sibling teams hold incompatible facts about the same system (scenario 4)
  contract_breach  new work moves past a contract's must-have date (scenario 2)
"""
import hashlib
import json
import re

from . import access, db, plans, watchers

P = db.ORG["people"]
S = db.ORG["scopes"]


def _norm(t):
    return re.sub(r"\s+", " ", t).strip()


def _cid(kind, *ids):
    return kind + "-" + hashlib.sha1("|".join(ids).encode()).hexdigest()[:8]


def upsert(c, replace=False):
    exists = db.q("SELECT status FROM conflicts WHERE id=?", (c["id"],))
    if exists and not (replace and exists[0]["status"] == "open"):
        return False
    db.x("INSERT OR REPLACE INTO conflicts (id, kind, trigger, scope, title, evidence, extra, route, options, visible_to, notify, created_at, "
         "origin, affected, actor, checks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
         (c["id"], c["kind"], c["trigger"], c["scope"], c["title"], json.dumps(c["evidence"]), c["extra"], c["route"],
          json.dumps(c["options"]), json.dumps(c["visible_to"]), json.dumps(c["notify"]), access.TODAY,
          c["origin"], json.dumps(c.get("affected", [])), c.get("actor"), json.dumps(c.get("checks")) if c.get("checks") else None))
    return not exists


def can_see(person, origin, affected, actor=None, private=False):
    """Conflicts show at your level and below, plus sideways when another team's work affects you.
    Members see conflicts in their own work, or ones that land on their own work. Nothing from above."""
    p = db.ORG["people"][person]
    if private:
        return actor == person
    if p.get("member"):
        return actor == person or any(access.below(a, p.get("own") or "-") for a in affected)
    area = p["access"]
    return access.below(origin, area) or any(access.below(a, area) for a in affected)


# --- rule checks: a hard rule, and the pattern of work that breaks it -----------------------------------
DRIFT_RULES = [
    {"subject": "release process", "rule": r"outside the release train unless .*sev1|only sev1",
     "breaks": r"(straight to production|instead of waiting for the .*train|outside the train)",
     "title": "Your plan ships a non-urgent fix outside the release train",
     "options": ["Wait for the next release train", "Mark it Sev1 with a reason", "Put the stalled ticket back on top"]},
]


def detect_drift():
    found = []
    drafts = db.q("SELECT * FROM items WHERE status='draft'")
    for d in drafts:
        member = next((pid for pid, p in P.items() if p.get("own") == d["scope"]), None)
        if not member:
            continue
        for rule in DRIFT_RULES:
            if not re.search(rule["breaks"], d["text"], re.I | re.S):
                continue
            ancestors = [a for a in S if access.below(d["scope"], a) and a != d["scope"]]
            hard = db.q(f"SELECT * FROM items WHERE strength='hard' AND status='current' AND scope IN ({','.join('?' * len(ancestors))})", ancestors)
            hit = next((h for h in hard if re.search(rule["rule"], h["text"], re.I | re.S)), None)
            if not hit:
                continue
            stalled = next((x for x in drafts if x["scope"] == d["scope"] and re.search(r"no progress on ([A-Z]+-\d+)", x["text"], re.I)), None)
            extra = ""
            if stalled:
                tk = re.search(r"no progress on ([A-Z]+-\d+) since (\S+?)\.?$", _norm(stalled["text"]), re.I)
                feeds = db.q("SELECT * FROM items WHERE scope=? AND text LIKE ? AND text LIKE '%contract%'", (S[d["scope"]] and access.parent(d["scope"]), f"%{tk.group(1)}%")) if tk else []
                extra = (f"Your assigned {tk.group(1)} has not moved since {tk.group(2)}." if tk else "") + \
                        (" It feeds a contract another department depends on." if feeds else "")
            lead = S[access.parent(d["scope"])]["owner"]
            found.append({"id": _cid("drift", d["id"], hit["id"]), "kind": "drift", "trigger": "drift_findings",
                          "scope": d["scope"], "title": rule["title"],
                          "evidence": [["Your notes (private)", _norm(d["text"]), d["source_id"]],
                                       [f"{S[hit['scope']]['name']} rule", _norm(hit["text"]), hit["source_id"]]],
                          "extra": extra.strip(),
                          "route": f"Only you see this. It reaches {P[lead]['name']} only if you push the plan to the team.",
                          "options": rule["options"], "visible_to": [member], "notify": [member],
                          "origin": d["scope"], "affected": [], "actor": member})
    return found


# --- incompatible facts between sibling teams ----------------------------------------------------------
VALUE_RULES = {  # subject -> list of (value, regex)
    "user id format": [("UUID strings", r"uuid"), ("integers", r"\binteger\b")],
}


def detect_team_clash():
    found = []
    teams = [s for s, m in S.items() if m["kind"] == "team"]
    for subject, values in VALUE_RULES.items():
        rows = [r for r in db.q("SELECT * FROM items WHERE status='current'") if subject in json.loads(r["subjects"]) and r["scope"] in teams]
        rows.sort(key=lambda r: (not re.search(r"fail|break|retire", r["text"], re.I), r["id"]))
        seen = set()
        def val(r):
            return next((v for v, rx in values if re.search(rx, r["text"], re.I)), None)
        for a in rows:
            for b in rows:
                if a["id"] == b["id"] or a["scope"] >= b["scope"] or access.parent(a["scope"]) != access.parent(b["scope"]):
                    continue
                va, vb = val(a), val(b)
                if not va or not vb or va == vb:
                    continue
                if not (a["type"] == "decision" or b["type"] == "decision"):
                    continue
                dec, dep = (a, b) if a["type"] == "decision" else (b, a)
                key = (dec["source_id"], dep["scope"])
                if key in seen:
                    continue
                seen.add(key)
                parent = access.parent(a["scope"])
                ct = db.q("SELECT * FROM contracts WHERE (provider=? AND consumer=?) OR (provider=? AND consumer=?)",
                          (dec["scope"], dep["scope"], dep["scope"], dec["scope"]))
                la, lb, sup = S[dec["scope"]]["owner"], S[dep["scope"]]["owner"], S[parent]["owner"]
                extra = "Each lead sees only the other team's passage this conflict rests on; the release is logged."
                if ct:
                    extra = f"It also breaks the {S[parent]['name']} contract “{ct[0]['title']}”: {ct[0]['must_have']} " + extra
                found.append({"id": _cid("clash", dec["source_id"], dep["scope"]), "kind": "team_clash", "trigger": "clashes",
                              "scope": parent,
                              "title": f"{S[dec['scope']]['name']}'s decision on {subject} breaks how {S[dep['scope']]['name']} works",
                              "evidence": [[S[dec["scope"]]["name"], _norm(dec["text"]), dec["source_id"]],
                                           [S[dep["scope"]]["name"], _norm(dep["text"]), dep["source_id"]]],
                              "extra": extra,
                              "route": f"Settled by {P[la]['name']} and {P[lb]['name']}. Escalates to {P[sup]['name']} if they disagree.",
                              "options": ["Return both formats for one release train",
                                          f"{S[dep['scope']]['name']} migrates in the same train with {S[dec['scope']]['name']}'s help",
                                          "Move the change to the next train"],
                              "visible_to": [la, lb, sup, "dana"], "notify": [la, lb],
                              "origin": dec["scope"], "affected": [dep["scope"]], "actor": la})
    return found


# --- new work that slips past a contract's must-have date ----------------------------------------------
QUARTER_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}


def detect_contract_breach():
    found = []
    for c in db.q("SELECT * FROM contracts WHERE must_have_date IS NOT NULL"):
        for it in db.q("SELECT * FROM items WHERE status='current'"):
            subj = json.loads(it["subjects"])
            if not any(s and s in subj for s in c["subject"].split(",")):
                continue
            t = _norm(it["text"])
            if not re.search(r"\b(move|slip|delay|push)\w*\b", t, re.I):
                continue
            dates = re.findall(r"\b(20\d\d-\d\d-\d\d)\b", t)
            qs = re.findall(r"\b(Q[1-4]) (20\d\d)\b", t)
            new = max(dates) if dates else (max(f"{y}-{QUARTER_END[q]}" for q, y in qs) if qs else None)
            if not new or new <= c["must_have_date"]:
                continue
            po, co = c["provider_owner"], c["consumer_owner"]
            found.append({"id": _cid("breach", c["id"], it["id"]), "kind": "contract_breach", "trigger": "contract_breaches",
                          "scope": c["scope"],
                          "title": f"New plan breaks the contract “{c['title']}”",
                          "evidence": [[S[it["scope"]]["name"], t, it["source_id"]],
                                       [f"Contract with {S.get(c['consumer'], {}).get('name', c['consumer'])}",
                                        "Must-have: " + c["must_have"], c["source_id"]]],
                          "extra": f"The proposal lands on {new}, after the must-have date of {c['must_have_date']}.",
                          "route": f"Negotiated between {P[po]['name']} and {P[co]['name']}. Escalates to {P['dana']['name']}.",
                          "options": ["Ship a reduced version by the must-have date", "Move one more engineer onto it",
                                      "Ask the customer side for a new date with a credit"],
                          "visible_to": [po, co, "dana"], "notify": [po, co],
                          "origin": it["scope"], "affected": [c["consumer"]] if c["consumer"] in S else [], "actor": po})
    return found


def run_detectors():
    new = []
    for det in (detect_drift, detect_team_clash, detect_contract_breach):
        for c in det():
            if upsert(c):
                new.append(c["id"])
    return new


def visible(person):
    rows = db.q("SELECT * FROM conflicts ORDER BY created_at, id")
    out = []
    for r in rows:
        if not can_see(person, r["origin"], json.loads(r["affected"] or "[]"), r["actor"], private=r["kind"] == "drift"):
            continue
        aff = json.loads(r["affected"] or "[]")
        p = db.ORG["people"][person]
        why = ("your own work" if r["actor"] == person else
               "your area" if access.below(r["origin"], p["access"]) and not p.get("member") else
               "another team's work that affects you")
        out.append({"id": r["id"], "kind": {"drift": "Drifting from SOP", "team_clash": "Team update breaks another team",
                                            "contract_breach": "Department commitment at risk",
                                            "pr": "Pull request off plan or policy"}[r["kind"]], "why": why,
                    "checks": json.loads(r["checks"]) if r["checks"] else None,
                    "trigger": r["trigger"], "to": ", ".join(P[p]["name"] for p in json.loads(r["notify"])),
                    "title": r["title"], "ev": json.loads(r["evidence"]), "extra": r["extra"], "route": r["route"],
                    "opts": json.loads(r["options"]), "resolved": r["decision"],
                    "action": json.loads(r["action_result"]) if r["action_result"] else None, "scope": r["scope"],
                    "plans": plans.plans_for(r), "watch": watchers.watch(r, person)})
    return out
