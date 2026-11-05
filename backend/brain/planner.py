"""Plan: tasks by day, moves checked for capacity, deadlines and dependencies, and load balancing."""
from . import access, db

CAP = db.ORG["capacity_hours_per_day"]
P = db.ORG["people"]


def days():
    import json
    return json.loads((db.DATA / db.ORG["company"] / "_plan.json").read_text())["days"]


def day_name(d):
    import datetime
    dt = datetime.date.fromisoformat(d)
    return dt.strftime("%a %b ") + str(dt.day)


def load(who, day, overrides=None):
    rows = db.q("SELECT id, hours, day FROM tasks WHERE who=?", (who,))
    return sum(r["hours"] for r in rows if (overrides or {}).get(r["id"], r["day"]) == day)


def visible_tasks(person, scope):
    out = []
    for t in db.q("SELECT * FROM tasks ORDER BY day, priority"):
        home = P[t["who"]]["home"]
        if access.below(home, scope) and access.can_read_scope(person, home):
            t["can_move"] = t["who"] == person or (not P[person].get("member") and access.below(home, P[person]["access"]))
            out.append(t)
    return out


def check_move(task_id, to):
    t = db.q("SELECT * FROM tasks WHERE id=?", (task_id,))[0]
    ov = {task_id: to}
    warn, notes, chain = [], [], None
    if load(t["who"], to, ov) > CAP:
        warn.append(f"{P[t['who']]['name']} would have {load(t['who'], to, ov):g} h on {day_name(to)}, over the {CAP} h day.")
    if t["critical"] and to > t["day"]:
        warn.append(f"This is on the critical path for the {t['critical']}. The owner of that contract will see the slip.")
    if t["feeds"]:
        d = db.q("SELECT * FROM tasks WHERE id=?", (t["feeds"],))[0]
        if d["day"] <= to:
            nxt = next((x for x in days() if x > to), to)
            warn.append(f"{P[d['who']]['name']}'s “{d['title']}” on {day_name(d['day'])} needs this first.")
            chain = {"task": d["id"], "title": d["title"], "to": nxt, "who": d["who"]}
    if t["needs"]:
        d = db.q("SELECT * FROM tasks WHERE id=?", (t["needs"],))[0]
        if d["day"] >= to:
            warn.append(f"This needs “{d['title']}” from {P[d['who']]['name']}, scheduled {day_name(d['day'])}.")
    if t["off_plan"] and to > t["day"]:
        notes.append("Good call: this work is outside the team plan, so later is safer.")
    return t, warn, notes, chain


def move(person, task_id, to):
    t, warn, notes, chain = check_move(task_id, to)
    if not (t["who"] == person or (not P[person].get("member") and access.below(P[t["who"]]["home"], P[person]["access"]))):
        return {"error": "You can move your own tasks, or tasks of people in your area."}
    db.x("UPDATE tasks SET day=? WHERE id=?", (to, task_id))
    db.audit(person, "move_task", {"task": task_id, "from": t["day"], "to": to, "warnings": warn}, access.TODAY)
    if chain:
        db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
             (chain["who"], f"“{t['title']}” moved to {day_name(to)}; your task depends on it.", task_id, access.TODAY))
    return {"task": task_id, "title": t["title"], "from": t["day"], "to": to, "warn": warn, "notes": notes, "chain": chain}


def balance(person, scope, apply=False):
    tasks = visible_tasks(person, scope)
    ov, moves = {}, []
    for who in sorted({t["who"] for t in tasks}):
        for d in days():
            while load(who, d, ov) > CAP:
                cand = sorted([t for t in tasks if t["who"] == who and ov.get(t["id"], t["day"]) == d and not t["critical"]],
                              key=lambda t: (-t["priority"], -t["hours"]))
                if not cand:
                    break
                c = cand[0]
                target = next((x for x in days() if x > d and load(who, x, ov) + c["hours"] <= CAP), days()[-1])
                if target == d:
                    break
                ov[c["id"]] = target
                moves.append({"task": c["id"], "title": c["title"], "who": who, "from": d, "to": target,
                              "why": f"off-plan ({c['off_plan'].lower()})" if c["off_plan"] else "lowest priority that day"})
    if apply:
        for m in moves:
            db.x("UPDATE tasks SET day=? WHERE id=?", (m["to"], m["task"]))
            db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
                 (m["who"], f"“{m['title']}” moved to {day_name(m['to'])} to balance load.", m["task"], access.TODAY))
        db.audit(person, "balance_apply", {"moves": moves}, access.TODAY)
    return {"moves": moves, "applied": apply}
