"""Work view for one unit: the timeline status bar, finished work (today, earlier this week, past week with a
summary), and the plan (today's open work, tomorrow, the rest of this week, next week), all from the brain."""
import datetime
import json
import re

from . import access, conflicts, db, planner


def _title(body):
    m = re.search(r"^# (.+)$", body, re.M)
    return m.group(1).strip() if m else body.strip().splitlines()[0][:90]


def _short(d):
    dt = datetime.date.fromisoformat(d)
    return dt.strftime("%b ") + str(dt.day)


def status(person, scope):
    if not access.can_read_scope(person, scope):
        return {"blocked": True, "scope_name": db.ORG["scopes"][scope]["name"],
                "owner": db.ORG["scopes"][scope]["owner"], "approvers": access.approvers_for(scope, person)}
    today = datetime.date.fromisoformat(access.TODAY)
    week_start = (today - datetime.timedelta(days=7)).isoformat()
    where, args = access.item_filter_sql(person)
    srcs = db.q(f"SELECT DISTINCT s.* FROM sources s JOIN items i ON i.source_id = s.id WHERE {where} "
                "AND (s.scope = ? OR s.scope LIKE ? || '/%') ORDER BY s.date DESC", args + [scope, scope])
    # git logs and decision logs carry their own dated entries
    dated = db.q(f"SELECT i.* FROM items i WHERE {where} AND (i.scope = ? OR i.scope LIKE ? || '/%') "
                 "AND i.type IN ('decision') AND i.date IS NOT NULL", args + [scope, scope])
    def entries(lo, hi):
        out = []
        for s in srcs:
            if s["date"] and lo <= s["date"] <= hi and s["source_type"] not in ("charter", "policy", "org_chart"):
                out.append([_short(s["date"]), _title(s["body"]), s["path"].split("/", 1)[1], s["date"]])
        for it in dated:
            if lo <= it["date"] <= hi and it["source_id"] not in {s["path"] for s in srcs if lo <= (s["date"] or "") <= hi}:
                out.append([_short(it["date"]), re.sub(r"\s+", " ", it["text"])[:120], it["source_id"].split("/", 1)[1], it["date"]])
        for a in db.q("SELECT * FROM audit WHERE action IN ('decide') AND ts BETWEEN ? AND ?", (lo, hi)):
            d = json.loads(a["detail"])
            if access.below(d.get("scope", "org"), scope) or access.below(scope, d.get("scope", "org")):
                out.append([_short(a["ts"]), f"Decision recorded: {d['option']}", "decided in the brain", a["ts"]])
        out.sort(key=lambda r: r[3], reverse=True)
        return [r[:3] for r in out][:8]
    yesterday = (today - datetime.timedelta(days=1)).isoformat()
    ms = [m for m in db.q("SELECT * FROM milestones ORDER BY date")
          if access.below(m["scope"], scope) or (scope != "org" and access.below(scope, m["scope"]) and m["risk"])]
    necks = []
    for c in conflicts.visible(person):
        if not c["resolved"] and (access.below(c["scope"], scope) or access.below(scope, c["scope"])):
            t = c["ev"][0][1]
            necks.append([c["title"], t if len(t) <= 140 else t[:t.rfind(" ", 0, 140)] + "…"])
    for t in planner.visible_tasks(person, scope):
        if planner.load(t["who"], t["day"]) > planner.CAP and not any(n[0].startswith(db.ORG["people"][t["who"]]["name"]) for n in necks):
            necks.append([f"{db.ORG['people'][t['who']]['name']} is over capacity on {planner.day_name(t['day'])}",
                          f"{planner.load(t['who'], t['day']):g} h planned against {planner.CAP} h."])
    for m in ms:
        if m["risk"] and m["progress"] < 40 and len(necks) < 6:
            necks.append([f"{m['label']} is {m['state'].lower()}", f"{m['progress']}% done; due {m['date']}."])
    return {"scope_name": db.ORG["scopes"][scope]["name"], "today": entries(access.TODAY, access.TODAY),
            "week": entries(week_start, yesterday),
            "timeline": [[m["date"], m["label"], m["progress"], m["state"], bool(m["risk"])] for m in ms],
            "necks": necks[:6], "tasks": planner.visible_tasks(person, scope), "days": planner.days(),
            "capacity": planner.CAP}


def _weeks():
    today = datetime.date.fromisoformat(access.TODAY)
    mon = today - datetime.timedelta(days=today.weekday())
    return today, mon, mon - datetime.timedelta(days=7), mon + datetime.timedelta(days=7)


def _summary(rows, label):
    """One deterministic paragraph: how much finished, by whom, grouped by unit."""
    if not rows:
        return f"Nothing finished {label} in this view."
    P, S = db.ORG["people"], db.ORG["scopes"]
    units = {}
    for r in rows:
        units.setdefault(S[P[r["who"]]["home"]]["name"], []).append(r)
    people = {r["who"] for r in rows}
    parts = [f"{u}: {'; '.join(x['title'] for x in v[:2])}" + (f" (+{len(v) - 2} more)" if len(v) > 2 else "")
             for u, v in sorted(units.items(), key=lambda kv: -len(kv[1]))]
    return (f"{len(rows)} piece{'s' if len(rows) != 1 else ''} of work finished {label} by {len(people)} "
            f"{'people' if len(people) != 1 else 'person'} across {len(units)} unit{'s' if len(units) != 1 else ''}. " + ". ".join(parts) + ".")


def work(person, scope):
    st = status(person, scope)
    if st.get("blocked"):
        return st
    P = db.ORG["people"]
    today, mon, last_mon, next_mon = _weeks()
    rows = [dict(r) for r in db.q("SELECT * FROM completed ORDER BY date DESC, time DESC")
            if access.below(P[r["who"]]["home"], scope) and access.can_read_scope(person, P[r["who"]]["home"])]
    for r in rows:
        r["name"] = P[r["who"]]["name"]
        r["unit"] = db.ORG["scopes"][P[r["who"]]["home"]]["name"]
    for a in db.q("SELECT * FROM audit WHERE action='decide' AND ts >= ?", (mon.isoformat(),)):
        d = json.loads(a["detail"])
        if access.below(d.get("scope", "org"), scope) and a["actor"] in P:
            rows.insert(0, {"who": a["actor"], "name": P[a["actor"]]["name"], "unit": db.ORG["scopes"][P[a["actor"]]["home"]]["name"],
                            "date": a["ts"][:10], "time": None, "title": f"Settled a conflict: {d['option']}", "ref": "decision written back to the brain"})
    t, m, lm = today.isoformat(), mon.isoformat(), last_mon.isoformat()
    done_today = [r for r in rows if r["date"] == t]
    done_week = [r for r in rows if m <= r["date"] < t]
    done_past = [r for r in rows if lm <= r["date"] < m]
    tom = (today + datetime.timedelta(days=1)).isoformat()
    nxt, after = next_mon.isoformat(), (next_mon + datetime.timedelta(days=7)).isoformat()
    tasks = st["tasks"]
    span = lambda a, b: f"{_short(a)} – {_short(b)}"
    st["work"] = {
        "range": {"week": span(m, (mon + datetime.timedelta(days=6)).isoformat()),
                  "past": span(lm, (mon - datetime.timedelta(days=1)).isoformat()),
                  "next": span(nxt, (next_mon + datetime.timedelta(days=6)).isoformat())},
        "done": {"today": done_today, "week": done_week, "past": done_past,
                 "summary": {"today": _summary(done_today, "today"), "week": _summary(done_today + done_week, "this week"),
                             "past": _summary(done_past, "last week")}},
        "plan": {"today": [x["id"] for x in tasks if x["day"] == t],
                 "tomorrow": [x["id"] for x in tasks if x["day"] == tom],
                 "week": [x["id"] for x in tasks if tom < x["day"] < nxt],
                 "next": [x["id"] for x in tasks if nxt <= x["day"] < after]},
        "today": t}
    return st
