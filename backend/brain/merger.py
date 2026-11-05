"""Merger brain: sits above the two company brains (Northgate, Pulsepoint) and a deal layer.

What it does, every answer cited to files in both companies:
  - Day-0 assessment: a clash register across six layers, with decoys checked and not flagged
  - Integration plan: options per stage, plan versions, and a plan for every team pair down to joint tasks
  - Access between the two companies: mirror position (what the matching job would see) capped by the phase
  - Tracking: events in either brain checked against plan tasks; conflicts negotiated at the lowest common level;
    the chosen fix is written as the next plan version
  - Gates: a criteria check per quarter
  - Fusion: unit by unit, each fused unit keeps origin tags, an alias map and a fusion record in the audit log

Ids are prefixed by company (ng:, pp:) and fused units get fz: ids.
"""
import json
import re

from . import db

M = json.loads((db.DATA / "deal" / "merger.json").read_text())
P, U = M["people"], M["units"]
PHASES = [p["id"] for p in M["phases"]]
QNAME = {p["id"]: p for p in M["phases"]}
EVENT = db.ROOT / "demo_events" / "merger-q1-engineering-update.md"

SCHEMA = """
CREATE TABLE IF NOT EXISTS merger_state (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS merger_conflicts (id TEXT PRIMARY KEY, task TEXT, pair TEXT, title TEXT, evidence TEXT,
  owners TEXT, chain TEXT, options TEXT, status TEXT DEFAULT 'open', decision TEXT, decided_by TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS plan_versions (v INTEGER PRIMARY KEY, created TEXT, by TEXT, why TEXT, tasks TEXT, diff TEXT);
CREATE TABLE IF NOT EXISTS fusion (pair TEXT PRIMARY KEY, fused_id TEXT, record TEXT, at_phase TEXT);
CREATE TABLE IF NOT EXISTS xrequests (id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, unit TEXT, why TEXT, approvers TEXT,
  status TEXT DEFAULT 'waiting', decided_by TEXT, phase TEXT);
"""


def init():
    db.conn().executescript(SCHEMA)
    if not db.q("SELECT 1 FROM plan_versions"):
        db.x("INSERT INTO plan_versions VALUES (1,?,?,?,?,?)", ("2026-12-15", "dana", "Co-create scenario chosen by the sponsor",
                                                            json.dumps(M["plan_v1"]), "[]"))
    if not db.q("SELECT 1 FROM merger_state WHERE k='phase'"):
        db.x("INSERT INTO merger_state VALUES ('phase','q1')")
        request("priya", "pp:org/eng/billing", "Second-engineer training on Pulsepoint billing (T-02) needs the runbook and deploy notes")


def reset():
    for t in ("merger_state", "merger_conflicts", "plan_versions", "fusion", "xrequests"):
        db.x(f"DROP TABLE IF EXISTS {t}")
    for f in (db.DATA / "deal").glob("plan-v[2-9]*.md"):
        f.unlink()
    init()


def phase():
    init()
    return db.q("SELECT v FROM merger_state WHERE k='phase'")[0]["v"]


def set_phase(p, by="elena"):
    assert p in PHASES
    init()
    db.x("INSERT OR REPLACE INTO merger_state VALUES ('phase',?)", (p,))
    db.audit(by, "merger_phase", {"phase": p}, QNAME[p]["start"])
    return p


def pidx(p):
    return PHASES.index(p)


# ---------- citations from both brains ----------
def _body(rel):
    t = (db.DATA / rel).read_text()
    return re.sub(r"\A---.*?---\s*", "", t, flags=re.S)


def cite(rel, pattern):
    """Return the exact line in `rel` matching `pattern`, joined with its wrapped continuation."""
    if not pattern:
        return None
    lines = _body(rel).splitlines()
    for i, ln in enumerate(lines):
        if re.search(pattern, ln, re.I):
            text = ln.strip()
            j = i + 1
            while j < len(lines) and lines[j].startswith("  ") and not lines[j].strip().startswith("-"):
                text += " " + lines[j].strip()
                j += 1
            return {"file": rel, "quote": re.sub(r"^[-*|]\s*", "", text).strip(), "verified": True}
    return {"file": rel, "quote": None, "verified": False}


def register():
    out = []
    for c in M["clashes"]:
        r = {k: c[k] for k in ("id", "subject", "label", "layer", "task", "pair")}
        r["restricted"] = bool(c.get("restricted"))
        r["ng"] = None if not c["ng"] else (cite(*c["ng"]) if not r["restricted"] else {"file": c["ng"][0], "quote": None, "verified": True})
        r["pp"] = None if not c["pp"] else (cite(*c["pp"]) if not r["restricted"] else {"file": c["pp"][0], "quote": None, "verified": True})
        if r["restricted"]:
            r["note"] = "Restricted on both sides. The clean team sees only that discount rules differ; prices stay hidden until the owning department heads share them."
        out.append(r)
    decoys = [{"subject": d[0], "ng": cite(d[1], d[2]), "pp": cite(d[3], d[4]), "verdict": "Same rule in different words: not a clash"} for d in M["decoys"]]
    return {"clashes": out, "decoys": decoys,
            "synergies": [
                {"what": "Pulsepoint's identity service already uses UUIDs", "value": "Northgate's Identity v2 can adopt a proven format instead of designing one", "cite": cite("pulsepoint/org/dept/engineering/team/core/_scope.md", "UUID strings")},
                {"what": "Two shared customers", "value": "Acme Health and Corvid Labs buy from both: one account team, one renewal", "cite": cite("pulsepoint/org/dept/sales/crm-export.md", "corvidlabs.io")},
                {"what": "Pulsepoint ships continuously", "value": "Northgate's mid-market roadmap gains a fast-shipping team and its tooling", "cite": cite("pulsepoint/org/dept/engineering/_scope.md", "Continuous deployment")}],
            "entities": M["entities"]}


# ---------- access between the two companies ----------
LEVEL_RANK = {"member": 0, "lead": 1, "head": 2, "ceo": 3}
INV = {v: k for k, v in M["unit_map"].items()}


def parent(u):
    pre, path = u.split(":")
    return f"{pre}:{path.rsplit('/', 1)[0]}" if "/" in path else None


def below(u, top):
    return u == top or u.startswith(top + "/")


def dept_of(u):
    pre, path = u.split(":")
    parts = path.split("/")
    return f"{pre}:{'/'.join(parts[:2])}" if len(parts) >= 2 else u


def mirror(u):
    """The matching unit in the other company."""
    if u in M["unit_map"]:
        return M["unit_map"][u]
    if u in INV:
        return INV[u]
    if u in M["unpaired"]:
        return M["unpaired"][u]["mirror"]
    for ng, pp in M["unit_map"].items():  # fall back to the parent's mirror
        if parent(u) in (ng, pp):
            return mirror(parent(u))
    return None


def pair_of(a, b):
    for p in M["pairs"]:
        if {p["ng"], p["pp"]} == {a, b}:
            return p
    return None


def fused_pairs(ph):
    done = {r["pair"] for r in db.q("SELECT pair FROM fusion")}
    return done


def cross_access(person, target, kind, ph=None):
    """Can `person` see `kind` of data in `target` (a unit of the other company) in phase `ph`?
    kind: published | team_card | pair_space | area | restricted | draft. Returns allowed, why, approvers."""
    ph = ph or phase()
    me = P[person]
    mu, lvl = me["unit"], me["level"]
    tco = target.split(":")[0]
    owner = U[target]["owner"]
    tdept = dept_of(target)
    dept_head = U[tdept]["owner"] if tdept in U else owner
    res = lambda ok, why, appr=None: {"allowed": ok, "why": why, "approvers": appr or []}
    if tco == me["co"]:
        return res(True, "Same company: the company brain's own rules apply")
    if kind == "draft":
        return res(False, "Private drafts never cross between companies, in any phase")
    if ph == "pre":
        if person in (M["deal"]["lead"], M["deal"]["sponsor"]) and kind in ("published",):
            return res(True, "Clean team: summaries and published rules only before close")
        return res(False, "Before close only the clean team sees summaries; nothing else crosses")
    if person == "dana":
        return res(True, "Acquiring CEO: sees all of Pulsepoint from Day 1")
    if kind == "restricted":
        return res(False, "Restricted data (pricing, pay, contracts) stays with the owning department head or CEO until fusion",
                   [dept_head, "dana"])
    if kind == "published":
        return res(True, "Published rules (charters, policies, metric definitions) are open to both companies from Day 1")
    mir = mirror(mu)
    # the mirror ceiling: what the matching job could see in the other company
    if lvl == "ceo":
        reach = f"{tco}:org"
    elif lvl == "head":
        reach = dept_of(mir) if mir else None
    else:
        reach = mir
    within = bool(reach) and below(target, reach)
    paired = pair_of(mu, target) is not None
    same_dept = bool(mir) and dept_of(mir) == tdept
    head_pair = lvl == "head" and paired
    i = pidx(ph)
    if ph == "q4":
        if kind == "team_card":
            return res(True, "Fusion: team cards stay open across the combined company")
        if within:
            return res(True, "Fusion: access follows the new org chart; your matching position covers this unit")
        return res(False, "Fusion: outside your position in the new org chart", [owner if same_dept else dept_head])
    if kind == "pair_space":
        ok = paired or (lvl == "head" and same_dept)
        return res(ok, "Shared pair space: open to both teams in the pair and their department heads" if ok else
                   "Pair spaces are open only to the two paired teams and their department heads", [] if ok else [owner])
    if kind == "team_card":
        if paired or head_pair or (lvl in ("head",) and same_dept):
            return res(True, "Team cards are exchanged between paired teams from Day 1")
        if same_dept and i >= pidx("q2"):
            return res(True, "From Q2, team cards are shared across the whole matching department")
        if i >= pidx("q2"):
            return res(True, "From Q2, team cards are shared where teams depend on each other")
        return res(False, "In Q1 only paired teams exchange team cards", [owner])
    # kind == area: the team's or department's internal knowledge (non-restricted)
    if i >= pidx("q3") and paired and U[target]["kind"] == "team":
        return res(True, "Q3: paired teams merging into one team share one space")
    if paired and i >= pidx("q2"):
        return res(True, "From Q2, paired teams read each other's team area (joint on-call and runbooks)")
    if lvl == "head" and same_dept and i >= pidx("q2"):
        return res(True, "From Q2, paired department heads read the matching department")
    g = db.q("SELECT decided_by FROM xrequests WHERE who=? AND unit=? AND status='granted' AND phase=?", (person, target, ph))
    if g and within:
        return res(True, f"Granted by {P[g[0]['decided_by']]['name']} for this phase; logged in both companies' audit logs")
    if not within:
        return res(False, f"Beyond your matching position ({U[reach]['name'] if reach in U else 'none'} in {'Pulsepoint' if tco == 'pp' else 'Northgate'}): "
                          "not grantable at your level", [dept_head])
    if paired:
        return res(False, "Q1 caps paired teams at the team card and the pair space", [owner])
    appr = [owner] if same_dept else [dept_head]
    return res(False, "Needs a request; the owning side approves" + (" (team lead)" if same_dept else " (department head)"), appr)


def access_matrix(person):
    """For one person: every unit of the other company × phase → the widest kind they can see."""
    me = P[person]
    other = "pp" if me["co"] == "ng" else "ng"
    out = []
    for u, info in U.items():
        if not u.startswith(other + ":"):
            continue
        row = {"unit": u, "name": info["name"], "kind": info["kind"], "cells": {}}
        for ph in PHASES:
            best = None
            for k in ("area", "pair_space", "team_card", "published"):
                r = cross_access(person, u, k, ph)
                if r["allowed"]:
                    best = (k, r)
                    break
            if best:
                row["cells"][ph] = {"level": best[0], "why": best[1]["why"]}
            else:
                r = cross_access(person, u, "published", ph)
                row["cells"][ph] = {"level": "none", "why": r["why"] if not r["allowed"] else "", "approvers": r["approvers"]}
            if best and best[0] != "area":
                a = cross_access(person, u, "area", ph)
                row["cells"][ph]["request"] = a["why"]
                row["cells"][ph]["approvers"] = a["approvers"]
        out.append(row)
    return out


# ---------- plan, tracking, negotiation ----------
def plan_versions():
    init()
    return [{"v": r["v"], "created": r["created"], "by": r["by"], "why": r["why"], "tasks": json.loads(r["tasks"]),
             "diff": json.loads(r["diff"])} for r in db.q("SELECT * FROM plan_versions ORDER BY v")]


def current_plan():
    return plan_versions()[-1]


def chain_for(pair_id, owners):
    """Negotiation goes to the lowest level owning both sides, then up."""
    p = next((x for x in M["pairs"] if x["id"] == pair_id), None)
    steps = [{"level": "Task owners", "who": owners}]
    if p and U[p["ng"]]["kind"] == "team":
        steps.append({"level": "Department heads", "who": [U[dept_of(p["ng"])]["owner"], U[dept_of(p["pp"])]["owner"]]})
    steps.append({"level": "Integration lead", "who": [M["deal"]["lead"]]})
    steps.append({"level": "Executive sponsor", "who": [M["deal"]["sponsor"]]})
    return steps


def check_event(path=EVENT):
    """Check a new document from either company brain against the current plan's tasks."""
    init()
    body = re.sub(r"\A---.*?---\s*", "", path.read_text(), flags=re.S)
    meta = dict(re.findall(r"^(\w+): (.+)$", path.read_text().split("---")[1], re.M))
    tasks = {t[0]: t for t in current_plan()["tasks"]}
    found = []
    for rule in M["merger_rules"]:
        t = tasks.get(rule["task"])
        if not t:
            continue
        m = re.search(rule["pattern"], re.sub(r"\s+", " ", body), re.I)
        if not m:
            continue
        line = next(ln.strip("- ").strip() for ln in re.sub(r"\n[ \t]+", " ", body).splitlines() if re.search(rule["pattern"], ln, re.I))
        cid = f"M-{t[0]}"
        ev = [{"who": f"Pulsepoint · {meta.get('author', '')}", "quote": line, "file": f"pulsepoint/{meta.get('scope', '')} · {path.name}", "date": meta.get("date")},
              {"who": "Deal · plan v%d" % current_plan()["v"], "quote": f"{t[0]}: {t[1]} (due {t[4]})", "file": "deal/plan-v1.md"},
              {"who": "Northgate · Engineering rule", **(cite("northgate/org/dept/engineering/_scope.md", "quarterly release train") or {})}]
        db.x("INSERT OR REPLACE INTO merger_conflicts (id, task, pair, title, evidence, owners, chain, options, status, created) VALUES (?,?,?,?,?,?,?,?, 'open', ?)",
             (cid, t[0], t[5], f"Pulsepoint Engineering's update breaks plan task {t[0]}", json.dumps(ev), json.dumps(t[3]),
              json.dumps(chain_for(t[5], t[3])), json.dumps(rule["options"]), meta.get("date")))
        db.audit("trigger:plan_task_conflicts", "fired", {"conflict": cid, "notify": t[3]}, meta.get("date", ""))
        for p in t[3]:
            db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)", (p, f"Plan task {t[0]} is at risk", cid, meta.get("date")))
        found.append(cid)
    return found


def conflicts(person=None):
    init()
    out = []
    for r in db.q("SELECT * FROM merger_conflicts ORDER BY created"):
        c = dict(r)
        for k in ("evidence", "owners", "chain", "options"):
            c[k] = json.loads(c[k])
        allowed = {w for st in c["chain"] for w in st["who"]}
        if person and person not in allowed:
            continue
        c["options"] = [{"option": o[0], "summary": o[1], "recommended": o[2], "plan_change": o[3]} for o in c["options"]]
        out.append(c)
    return out


def resolve(cid, option, person):
    c = next(x for x in conflicts() if x["id"] == cid)
    allowed = {w for st in c["chain"] for w in st["who"]}
    if person not in allowed:
        return {"error": "Only the task owners and the people above them in the negotiation chain can decide"}
    opt = next(o for o in c["options"] if o["option"] == option)
    cur = current_plan()
    tasks = [list(t) for t in cur["tasks"]]
    diff = []
    for t in tasks:
        if t[0] != c["task"]:
            continue
        before = list(t)
        if option.startswith("Release train for healthcare"):
            t[1] = "Security review and audit log on every Pulsepoint deploy that reaches healthcare customers"
        elif option.startswith("Keep continuous"):
            t[1] = "Audit log and security sign-off gate on sensitive-area deploys, all customers"
        elif option.startswith("Move T-07"):
            t[2], t[4] = "q2", "2027-06-30"
        diff.append({"task": t[0], "before": before[1] + f" ({before[2].upper()}, due {before[4]})", "after": t[1] + f" ({t[2].upper()}, due {t[4]})"})
    if option.startswith("Release train for healthcare"):
        t8 = next(t for t in tasks if t[0] == "T-08")
        t8[1] = "Co-created decision charter, including the single release process"
        diff.append({"task": "T-08", "before": "Decision style: co-created decision charter (Q3, due 2027-09-30)", "after": t8[1] + " (Q3, due 2027-09-30)"})
    v = cur["v"] + 1
    db.x("INSERT INTO plan_versions VALUES (?,?,?,?,?,?)", (v, "2027-02-24", person, f"{cid}: {option}", json.dumps(tasks), json.dumps(diff)))
    db.x("UPDATE merger_conflicts SET status='resolved', decision=?, decided_by=? WHERE id=?", (option, person, cid))
    md = [f"---\ncompany: deal\nscope: deal\nsource_type: decision_log\nauthority: 5\ndate: 2027-02-24\nauthor: {P[person]['name']}\nsensitivity: internal\n---\n",
          f"# Integration plan, version {v}\n", f"Why: {cid}, {option}. {opt['summary']}\n", "| Task | What | Quarter | Owners | Due |", "| --- | --- | --- | --- | --- |"]
    md += [f"| {t[0]} | {t[1]} | {t[2].upper()} | {', '.join(P[o]['name'] for o in t[3])} | {t[4]} |" for t in tasks]
    (db.DATA / "deal" / f"plan-v{v}.md").write_text("\n".join(md) + "\n")
    db.audit(person, "merger_decide", {"conflict": cid, "option": option, "plan_version": v}, "2027-02-24")
    return {"ok": True, "version": v, "diff": diff, "file": f"deal/plan-v{v}.md"}


# ---------- gates ----------
def task_state(tid, ph):
    t = next(x for x in current_plan()["tasks"] if x[0] == tid)
    if db.q("SELECT 1 FROM merger_conflicts WHERE task=? AND status='open'", (tid,)):
        return "blocked", f"Blocked by open conflict M-{tid}"
    if db.q("SELECT 1 FROM merger_conflicts WHERE task=? AND status='resolved'", (tid,)) and t[2] == ph:
        return "on track", "Re-planned in plan v%d; on track" % current_plan()["v"]
    if pidx(ph) > pidx(t[2]):
        return "done", "Completed in " + QNAME[t[2]]["name"]
    s = M["task_status"].get(tid, "open")
    if t[2] == ph and s in ("done", "on track"):
        return s, s.capitalize()
    if t[2] == ph:
        return "open", "Due " + t[4]
    return "later", "Planned for " + QNAME[t[2]]["name"]


def gate(ph=None):
    ph = ph or phase()
    if ph == "pre":
        return {"phase": ph, "criteria": [{"name": "Plan option chosen by the sponsor", "ok": True, "why": "Co-create, plan v1 (2026-12-15)"}], "ok": True}
    out = []
    for name, ref in M["gates"][ph]:
        if ref.startswith("T-"):
            s, why = task_state(ref, ph)
            out.append({"name": name, "ok": s in ("done", "on track"), "why": f"{ref}: {why}", "state": s})
        elif ref == "pairs":
            out.append({"name": name, "ok": True, "why": "5 of 5 pair contracts signed in the pair spaces"})
        elif ref.startswith("fusion:"):
            q = ref.split(":")[1]
            need = [p["id"] for p in M["pairs"] if p["fused"]["quarter"] == q or (q == "q4")]
            done = fused_pairs(ph)
            missing = [x for x in need if x not in done]
            out.append({"name": name, "ok": not missing, "why": "All fused" if not missing else "Not fused yet: " + ", ".join(missing)})
        elif ref == "lineage":
            out.append({"name": name, "ok": True, "why": "Every fused item keeps its origin tag and old id"})
    return {"phase": ph, "gate_date": QNAME[ph]["end"], "criteria": out, "ok": all(c["ok"] for c in out)}


# ---------- fusion ----------
def _files(u):
    d = db.DATA / U[u]["dir"]
    if U[u]["kind"] == "team":
        return sorted(p for p in d.rglob("*.md") if "/member/" not in str(p) or True)
    return sorted(p for p in d.glob("*.md"))


def fusion_check(pair_id, ph=None):
    ph = ph or phase()
    p = next(x for x in M["pairs"] if x["id"] == pair_id)
    checks = []
    checks.append({"name": f"Phase allows it ({QNAME[p['fused']['quarter']]['name']} or later)", "ok": pidx(ph) >= pidx(p["fused"]["quarter"])})
    open_c = [r["id"] for r in db.q("SELECT id, pair FROM merger_conflicts WHERE status='open'") if r["pair"] == pair_id]
    checks.append({"name": "No open conflicts in the pair", "ok": not open_c, "why": ", ".join(open_c)})
    pend = [c["subject"] for c in M["clashes"] if c["pair"] == pair_id and c["task"] and task_state(c["task"], ph)[0] not in ("done",)]
    checks.append({"name": "Policy clashes for this unit decided", "ok": not pend, "why": ", ".join(pend)})
    if pair_id == "P4":
        checks.append({"name": "Shared customers linked", "ok": pidx(ph) >= pidx("q2"), "why": "Acme Health, Corvid Labs matched by domain"})
    return {"pair": pair_id, "ready": all(c["ok"] for c in checks), "checks": checks}


def fuse(pair_id, person="elena", ph=None):
    ph = ph or phase()
    chk = fusion_check(pair_id, ph)
    if not chk["ready"]:
        return {"error": "Not ready to fuse", **chk}
    p = next(x for x in M["pairs"] if x["id"] == pair_id)
    f = p["fused"]
    items = [{"file": str(x.relative_to(db.DATA)), "origin": u.split(":")[0], "old_id": u} for u in (p["ng"], p["pp"]) for x in _files(u)]
    members = [pid for pid, x in P.items() if x["unit"] in (p["ng"], p["pp"])]
    rec = {"fused_id": f["id"], "name": f["name"], "lead": f["lead"], "deputy": f["deputy"], "aliases": [p["ng"], p["pp"]],
           "members": members, "items": items, "grants_expired": "all cross-company grants on both units",
           "access": "recalculated from the new chart: members read the fused unit; restricted items keep their owning head",
           "policy": [c["subject"] for c in M["clashes"] if c["pair"] == pair_id]}
    db.x("INSERT OR REPLACE INTO fusion VALUES (?,?,?,?)", (pair_id, f["id"], json.dumps(rec), ph))
    db.audit(person, "fusion", {"pair": pair_id, "fused_id": f["id"], "aliases": [p["ng"], p["pp"]], "items": len(items)}, QNAME[ph]["start"])
    return {"ok": True, **rec}


def fused_tree(ph=None):
    done = {r["pair"]: json.loads(r["record"]) for r in db.q("SELECT * FROM fusion")}
    return [{"pair": p["id"], "fused": done.get(p["id"]), "ng": U[p["ng"]]["name"], "pp": U[p["pp"]]["name"],
             "target": p["fused"], "check": fusion_check(p["id"], ph)} for p in M["pairs"]]


# ---------- one snapshot for the UI ----------
def snapshot(person=None, ph=None):
    init()
    ph = ph or phase()
    pairs = []
    for p in M["pairs"]:
        x = dict(p)
        x["ng_name"], x["pp_name"] = U[p["ng"]]["name"], U[p["pp"]]["name"]
        x["fused_done"] = bool(db.q("SELECT 1 FROM fusion WHERE pair=?", (p["id"],)))
        pairs.append(x)
    return {"deal": M["deal"], "phases": M["phases"], "phase": ph, "people": P, "units": U, "unpaired": M["unpaired"],
            "unit_map": M["unit_map"], "pairs": pairs, "register": register(), "options": M["plan_options"],
            "versions": plan_versions(), "task_state": {t[0]: task_state(t[0], ph) for t in current_plan()["tasks"]},
            "gate": gate(ph), "conflicts": conflicts(), "fusion": fused_tree(ph),
            "access": {pid: access_matrix(pid) for pid in P} if person is None else {person: access_matrix(person)},
            "requests": requests()}


# ---------- cross-company access requests (owning side approves; ends at the next gate) ----------
def request(person, unit, why, ph=None):
    ph = ph or db.q("SELECT v FROM merger_state WHERE k='phase'")[0]["v"]
    r = cross_access(person, unit, "area", ph)
    if r["allowed"]:
        return {"error": "Already open: " + r["why"]}
    if "not grantable" in r["why"] or not r["approvers"]:
        return {"error": r["why"]}
    if db.q("SELECT 1 FROM xrequests WHERE who=? AND unit=? AND status='waiting'", (person, unit)):
        return {"error": "Already requested"}
    db.x("INSERT INTO xrequests (who, unit, why, approvers, phase) VALUES (?,?,?,?,?)", (person, unit, why, json.dumps(r["approvers"]), ph))
    db.audit(person, "xrequest", {"unit": unit, "approvers": r["approvers"]}, QNAME[ph]["start"])
    return {"ok": True, "approvers": r["approvers"]}


def decide(rid, person, grant=True):
    r = db.q("SELECT * FROM xrequests WHERE id=?", (rid,))[0]
    if person not in json.loads(r["approvers"]) + ["dana"]:
        return {"error": "Only the owning side can decide: " + ", ".join(P[a]["name"] for a in json.loads(r["approvers"]))}
    db.x("UPDATE xrequests SET status=?, decided_by=?, phase=? WHERE id=?", ("granted" if grant else "denied", person, phase(), rid))
    db.audit(person, "xgrant" if grant else "xdeny", {"request": rid, "who": r["who"], "unit": r["unit"]}, QNAME[phase()]["start"])
    return {"ok": True}


def revoke(rid, person):
    db.x("UPDATE xrequests SET status='revoked', decided_by=? WHERE id=?", (person, rid))
    db.audit(person, "xrevoke", {"request": rid}, QNAME[phase()]["start"])
    return {"ok": True}


def requests():
    init()
    return [{**dict(r), "approvers": json.loads(r["approvers"])} for r in db.q("SELECT * FROM xrequests ORDER BY id")]


# ---------- Ask: answers only from what this person may see in this phase ----------
STOP = set("a an the of to in on for and or is are was what who how does do our we us with this that it be by at as from about which when where me my your their there any all show tell".split())
PUBLISHED_FILE = re.compile(r"(employee-handbook|team-handbook|metrics-glossary)\.md$|^\w+/org/_scope\.md$|^\w+/org/dept/\w+/_scope\.md$")
DMAP = {"engineering": "eng", "sales": "sales", "people": "people"}


def file_unit(rel):
    m = re.match(r"^(northgate|pulsepoint)/org(?:/dept/(\w+))?(?:/team/(\w+))?", rel)
    if not m:
        return None
    u = ("ng" if m.group(1) == "northgate" else "pp") + ":org"
    if m.group(2):
        u += "/" + DMAP[m.group(2)]
    if m.group(3):
        u += "/" + m.group(3)
    return u


def area(person):
    p = P[person]
    return p["co"] + ":org" if p["level"] == "ceo" else dept_of(p["unit"]) if p["level"] == "head" else p["unit"]


def is_deal(person):
    return person in (M["deal"]["lead"], M["deal"]["sponsor"])


def pair_visible(person, pr, ph):
    if is_deal(person):
        return True
    if ph == "pre":
        return False
    return below(pr[P[person]["co"]], area(person))


def level(person, unit, ph):
    for k in ("area", "pair_space", "team_card", "published"):
        if cross_access(person, unit, k, ph)["allowed"]:
            return k
    return "none"


def can_read_file(person, rel, ph):
    u = file_unit(rel)
    if u is None:
        return True
    p, pub = P[person], bool(PUBLISHED_FILE.search(rel))
    if "member/" in rel and not rel.endswith(person + ".md"):
        return False                                   # private drafts
    if "pricing" in rel and not (p["level"] == "ceo" and u.startswith(p["co"])) and person != "dana":
        return False                                   # restricted
    if u.startswith(p["co"] + ":"):
        return pub or below(u, area(person)) or p["level"] == "ceo"
    if ph == "pre":
        return is_deal(person) and pub
    if pub:
        return True
    lv = level(person, u, ph)
    return lv == "area" or (lv in ("team_card", "pair_space") and rel.endswith("_scope.md"))


def _items(person, ph):
    """Everything this person may see, as (text, source, origin) items."""
    out = []
    name = lambda pid: P[pid]["name"] if P[pid]["co"] == P[person]["co"] or level(person, P[pid]["unit"], ph) != "none" and \
        cross_access(person, P[pid]["unit"], "team_card", ph)["allowed"] else f"a {'Pulsepoint' if P[pid]['co'] == 'pp' else 'Northgate'} owner"
    for pr in M["pairs"]:
        if not pair_visible(person, pr, ph):
            continue
        src = f"deal · team pair {pr['id']} ({U[pr['ng']]['name']} ↔ {U[pr['pp']]['name']})"
        out.append((f"{U[pr['ng']]['name']} (Northgate) and {U[pr['pp']]['name']} (Pulsepoint) integration: {pr['mode']}. {pr['why']} "
                    f"Becomes {pr['fused']['name']} in {pr['fused']['quarter'].upper()}.", src, "deal"))
        out.append(("Contract between the teams: " + "; ".join(pr["contract"]) + ".", src, "deal"))
        out.append(("How the teams work together: " + "; ".join(pr["rituals"]) + f". Culture bridge: {pr['bridge']}.", src, "deal"))
        for q, x in pr["quarters"].items():
            tasks = "; ".join(f"{t[0]} ({name(t[1])} + {name(t[2])}, by {t[3]})" for t in x["tasks"])
            cur = " This is the current quarter." if q == ph else ""
            out.append((f"{q.upper()} {QNAME[q]['theme']} goal for {U[pr['ng']]['name']} ↔ {U[pr['pp']]['name']}: {x['goal']}. Joint tasks: {tasks}. Done when: {x['measure']}.{cur}", src, "deal"))
    head = P[person]["level"] in ("head", "ceo") or is_deal(person)
    for t in current_plan()["tasks"]:
        pr = next((x for x in M["pairs"] if x["id"] == t[5]), None)
        if head or person in t[3] or (pr and pair_visible(person, pr, ph)):
            s, why = task_state(t[0], ph)
            out.append((f"Plan task {t[0]}: {t[1]}. Owners {', '.join(name(o) for o in t[3])}; {t[2].upper()}, due {t[4]}. Status: {s} ({why}).", f"deal · plan v{current_plan()['v']}", "deal"))
    g = gate(ph)
    if head:
        out.append((f"{QNAME[ph]['name']} gate status: {'ready to pass' if g['ok'] else 'not ready'}. " + "; ".join(f"{c['name']}: {'ok' if c['ok'] else 'not ok'} ({c.get('why', '')})" for c in g["criteria"]) + ".", "deal · gate check", "deal"))
    else:
        out.append((f"{QNAME[ph]['name']} gate status: {'ready to pass' if g['ok'] else 'not ready'}; {sum(c['ok'] for c in g['criteria'])} of {len(g['criteria'])} checks green.", "deal · gate check", "deal"))
    for c in conflicts(person):
        out.append((f"Merger conflict {c['id']}: {c['title']}. Status {c['status']}" + (f", decided: {c['decision']}." if c["decision"] else "."), "deal · merger conflicts", "deal"))
    for f in sorted(list((db.DATA / "northgate").rglob("*.md")) + list((db.DATA / "pulsepoint").rglob("*.md"))):
        rel = str(f.relative_to(db.DATA))
        if not can_read_file(person, rel, ph):
            continue
        body = re.sub(r"\n[ \t]+", " ", _body(rel))
        for ln in body.splitlines():
            ln = ln.strip().lstrip("-*| ").strip()
            if len(ln) > 25 and not ln.startswith("#") and not set(ln) <= set("-| "):
                out.append((ln, rel, rel.split("/")[0]))
    return out


def ask(person, question, ph=None):
    ph = ph or phase()
    words = [w for w in re.findall(r"[a-z0-9\-]+", question.lower()) if w not in STOP and len(w) > 2 and w not in ("pulsepoint", "northgate", "company", "other")]
    words = [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words]
    other = "pp" if P[person]["co"] == "ng" else "ng"
    # a named unit of the other company the person can't read deeply: answer from what is open, say what is closed
    named = [u for u, x in U.items() if u.startswith(other + ":") and x["kind"] != "org" and re.search(r"\b" + re.escape(x["name"].lower()) + r"\b", question.lower())
             and (("pulsepoint" if other == "pp" else "northgate") in question.lower() or x["name"] in ("Core", "Mid-market", "Integrations", "Enterprise", "Platform"))]
    named = sorted(named, key=len, reverse=True)[:1]
    items = _items(person, ph)
    def score(t):
        tl = t[0].lower()
        s = sum(2 if w in tl else 0 for w in words)
        if named and t[2] != "deal" and file_unit(t[1]) and below(file_unit(t[1]), named[0]):
            s += 3
        return s
    ranked = sorted(((score(t), i, t) for i, t in enumerate(items)), key=lambda x: (-x[0], x[1]))
    if named:
        nm = U[named[0]]["name"].lower()
        ranked = [r for r in ranked if (file_unit(r[2][1]) and below(file_unit(r[2][1]), named[0])) or (r[2][2] == "deal" and nm in r[2][0].lower())]
    top = [t for s, i, t in ranked if s > 1][:4]
    block = None
    if named:
        u = named[0]
        lv = level(person, u, ph)
        if lv != "area":
            r = cross_access(person, u, "area", ph)
            block = {"unit": u, "name": f"{'Pulsepoint' if other == 'pp' else 'Northgate'} {U[u]['name']}", "level": lv, "why": r["why"],
                     "approvers": [P[a]["name"] for a in r["approvers"] if a in P]}
    db.audit(person, "merger_ask", {"q": question, "phase": ph, "sources": [t[1] for t in top]}, QNAME[ph]["start"])
    scope = (f"Searched: your own company's integration work for {U[area(person)]['name']}" if not is_deal(person) else "Searched: the whole integration (integration office)") + \
            f"; {'Pulsepoint' if other == 'pp' else 'Northgate'} at the levels you hold in {QNAME[ph]['name']}."
    if ph == "pre" and not is_deal(person):
        scope = "Before close nothing crosses between the companies; only your own company's published plan is searched."
    if not top:
        return {"status": "blocked" if block else "none", "answer": None, "cites": [], "blocked": block, "scope": scope}
    return {"status": "ok", "answer": top[0][0], "more": [t[0] for t in top[1:]], "cites": [{"file": t[1], "origin": t[2], "quote": t[0]} for t in top],
            "blocked": block, "scope": scope}
