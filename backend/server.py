"""Northgate Brain backend: a standard-library HTTP server (no installs needed).

Run:  python3 backend/server.py            then open http://localhost:8000
Env:  ANTHROPIC_API_KEY   optional, Claude writes the answers (otherwise extractive answers)
      GITHUB_REPO, GITHUB_TOKEN   optional, approved decisions create real GitHub issues
      TRIGGERWARE_URL     optional, default localhost:5221
"""
import json
import pathlib
import shutil
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from brain import merger, access, actions, ask, conflicts, db, ingest, llm, planner, plans, prcheck, status, triggers, watchers  # noqa: E402

WEB = db.ROOT / "web" / "index.html"
DEMO = db.ROOT / "demo_events"
P = db.ORG["people"]


def boot():
    report = ingest.ingest_all()
    fired = triggers.run()
    tw = triggers.BRIDGE.register()
    return {"files": len(report), "quarantined": [r["path"] for r in report if r.get("quarantined")],
            "triggers": fired, "triggerware": tw}


# ---------------------------------------------------------------- handlers
def h_org(qs, body):
    scopes = {k: {kk: v[kk] for kk in ("name", "kind", "owner")} for k, v in db.ORG["scopes"].items() if v["kind"] != "member"}
    people = {k: {kk: v.get(kk) for kk in ("name", "role", "home", "access", "member")} for k, v in P.items()}
    return {"scopes": scopes, "people": people, "today": access.TODAY,
            "model": "claude" if llm.available() else "extractive", "triggerware": triggers.BRIDGE.status}


def h_ask(qs, body):
    return ask.ask(body["person"], body["question"])


def h_status(qs, body):
    return status.work(qs["person"], qs["scope"])


def h_conflicts(qs, body):
    return conflicts.visible(qs["person"])


def h_resolve(qs, body, cid):
    person, option = body["person"], body["option"]
    c = db.q("SELECT * FROM conflicts WHERE id=?", (cid,))
    if not c or not conflicts.can_see(person, c[0]["origin"], json.loads(c[0]["affected"] or "[]"), c[0]["actor"], c[0]["kind"] == "drift"):
        return {"error": "Not found"}
    c = c[0]
    changes = plans.apply(c, option, person)
    path, rep = actions.write_decision(c, option, person, plans.plans_for(c))
    issue = None
    if c["kind"] != "drift":   # private drift stays private: no shared issue
        ev = json.loads(c["evidence"])
        issue = actions.github_issue(f"[Brain] {c['title']}: {option}",
                                     f"Decision: **{option}**\n\nDecided by {P[person]['name']} on {access.TODAY}.\n\n"
                                     + "\n".join(f"- {e[0]}: “{e[1]}” ({e[2]})" for e in ev)
                                     + f"\n\nRaised by the `{c['trigger']}` trigger.")
    result = {"decision_file": path, "issue": issue, "task_changes": changes}
    db.x("UPDATE conflicts SET status='resolved', decision=?, decided_by=?, decided_at=?, action_result=? WHERE id=?",
         (option, person, access.TODAY, json.dumps(result), cid))
    db.audit(person, "decide", {"conflict": cid, "option": option, "scope": c["scope"], "result": result}, access.TODAY)
    for n in json.loads(c["notify"]):
        if n != person:
            db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
                 (n, f"Decided by {P[person]['name']}: {option}", cid, access.TODAY))
    triggers.run()
    return {"ok": True, **result}


def h_nudge(qs, body, cid):
    person = body["person"]
    c = db.q("SELECT * FROM conflicts WHERE id=?", (cid,))[0]
    if not conflicts.can_see(person, c["origin"], json.loads(c["affected"] or "[]"), c["actor"], c["kind"] == "drift"):
        return {"error": "Not found"}
    to = watchers.watch(c, person)["nudge"]
    db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
         (to, f"{P[person]['name']} asks you to pick up: {c['title']}", cid, access.TODAY))
    db.audit(person, "nudge", {"conflict": cid, "to": to}, access.TODAY)
    return {"ok": True, "to": to}


def h_tasks_move(qs, body, tid):
    return planner.move(body["person"], tid, body["to"])


def h_balance(qs, body):
    return planner.balance(body["person"], body["scope"], bool(body.get("apply")))


def h_governance(qs, body):
    me = qs["person"]
    reqs = db.q("SELECT * FROM requests WHERE status='waiting' ORDER BY id")
    for r in reqs:
        r["approvers"] = json.loads(r["approvers"])
    grants = db.q("SELECT * FROM grants WHERE revoked=0 AND expires>? ORDER BY id", (access.TODAY,))
    cols = [s for s, m in db.ORG["scopes"].items() if m["kind"] in ("dept", "team")]
    matrix = {pid: {s: ("own" if access.below(s, P[pid]["access"]) else
                        "grant" if any(g["who"] == pid and access.below(s, g["scope"]) for g in grants) else "none")
                    for s in cols} for pid in P}
    return {"pending": [r for r in reqs if me in r["approvers"]], "mine": [r for r in reqs if r["who"] == me],
            "grants": grants, "matrix": matrix, "cols": cols,
            "notifications": db.q("SELECT * FROM notifications WHERE to_person=? ORDER BY id DESC LIMIT 20", (me,))}


def h_request(qs, body):
    who, scope = body["person"], body["scope"]
    if access.can_read_scope(who, scope):
        return {"error": "You already have access."}
    if db.q("SELECT 1 FROM requests WHERE who=? AND scope=? AND status='waiting'", (who, scope)):
        return {"ok": True, "duplicate": True}
    appr = access.approvers_for(scope, who)
    label = f"{db.ORG['scopes'][access.parent(scope)]['name'] if access.parent(scope) else 'Northgate'} / {db.ORG['scopes'][scope]['name']}"
    db.x("INSERT INTO requests (who, scope, label, why, approvers, created_at) VALUES (?,?,?,?,?,?)",
         (who, scope, body.get("label") or label, body.get("why", ""), json.dumps(appr), access.TODAY))
    for a in appr:
        db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
             (a, f"{P[who]['name']} requests access to {label}", scope, access.TODAY))
    db.audit(who, "request_access", {"scope": scope, "approvers": appr}, access.TODAY)
    return {"ok": True, "approvers": appr}


def h_grant(qs, body, rid):
    me = body["person"]
    r = db.q("SELECT * FROM requests WHERE id=?", (int(rid),))[0]
    if me not in json.loads(r["approvers"]):
        return {"error": "You can't grant this request."}
    import datetime
    exp = (datetime.date.fromisoformat(access.TODAY) + datetime.timedelta(days=int(body.get("days", 30)))).isoformat()
    db.x("INSERT INTO grants (who, scope, label, granted_by, expires, request_id) VALUES (?,?,?,?,?,?)",
         (r["who"], r["scope"], r["label"], me, exp, r["id"]))
    db.x("UPDATE requests SET status='granted', decided_by=? WHERE id=?", (me, r["id"]))
    db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
         (r["who"], f"{P[me]['name']} granted {r['label']} until {exp}", r["scope"], access.TODAY))
    db.audit(me, "grant", {"request": r["id"], "who": r["who"], "scope": r["scope"], "expires": exp}, access.TODAY)
    return {"ok": True, "expires": exp}


def h_deny(qs, body, rid):
    me = body["person"]
    r = db.q("SELECT * FROM requests WHERE id=?", (int(rid),))[0]
    if me not in json.loads(r["approvers"]):
        return {"error": "You can't decide this request."}
    db.x("UPDATE requests SET status='denied', decided_by=? WHERE id=?", (me, r["id"]))
    db.audit(me, "deny", {"request": r["id"]}, access.TODAY)
    return {"ok": True}


def h_revoke(qs, body, gid):
    me = body["person"]
    g = db.q("SELECT * FROM grants WHERE id=?", (int(gid),))[0]
    if me not in (g["granted_by"], "dana"):
        return {"error": "Only the person who granted it, or the CEO, can revoke it."}
    db.x("UPDATE grants SET revoked=1 WHERE id=?", (g["id"],))
    db.audit(me, "revoke", {"grant": g["id"]}, access.TODAY)
    return {"ok": True}


def h_demo_event(qs, body):
    """Drop a demo event file into the brain, as if someone had just written it, and run the triggers."""
    name = body.get("name", "sso-slip")
    src = DEMO / f"{name}.md"
    meta, _, _ = ingest.parse_front_matter(src.read_text())
    dst_dir = db.DATA / db.ORG["company"] / meta["scope"]
    if meta.get("company") != db.ORG["company"]:
        return {"error": "That event belongs to another company."}
    dst = dst_dir / f"{name}.md"
    shutil.copy(src, dst)
    rep = ingest.ingest_file(dst)
    return {"ingested": rep, "fired": triggers.run()}


def h_pr(qs, body):
    """A pull request to check: {"demo": 4431} for a sample, or a GitHub pull_request webhook payload."""
    if "pull_request" in body:
        r = prcheck.from_github(body)
    else:
        pr = json.loads((DEMO / "prs" / f"pr-{int(body['demo'])}.json").read_text())
        r = prcheck.run(pr)
    r["fired"] = triggers.run()
    return r


def h_prs(qs, body):
    return prcheck.visible_prs(qs["person"])


def h_health(qs, body):
    ok, bad = db.verify_audit()
    return {"items": db.q("SELECT count(*) n FROM items")[0]["n"], "audit_chain_ok": ok, "audit_break_at": bad,
            "model": "claude" if llm.available() else "extractive", "triggerware": triggers.BRIDGE.status}


def h_reset(qs, body):
    for d in (db.DATA / db.ORG["company"]).rglob("decisions"):
        shutil.rmtree(d)
    for name in ("sso-slip",):
        for f in (db.DATA / db.ORG["company"]).rglob(f"{name}.md"):
            f.unlink()
    merger.reset()
    return boot()


def h_merger(qs, body):
    return merger.snapshot(None, qs.get("phase"))


def h_merger_phase(qs, body):
    return {"phase": merger.set_phase(body["phase"], body.get("person", "elena")), "gate": merger.gate()}


def h_merger_event(qs, body):
    return {"conflicts": merger.check_event()}


def h_merger_resolve(qs, body, cid):
    return merger.resolve(cid, body["option"], body["person"])


def h_merger_fuse(qs, body, pid):
    return merger.fuse(pid, body.get("person", "elena"))


def h_merger_access(qs, body):
    return merger.cross_access(qs["person"], qs["unit"], qs.get("kind", "area"), qs.get("phase"))


def h_xreq(qs, body):
    return merger.request(body["person"], body["unit"], body.get("why", ""))


def h_xgrant(qs, body, rid):
    return merger.decide(int(rid), body["person"], True)


def h_xdeny(qs, body, rid):
    return merger.decide(int(rid), body["person"], False)


def h_xrevoke(qs, body, rid):
    return merger.revoke(int(rid), body["person"])


def h_tw_rows(qs, body):
    return triggers.rows_for_triggerware()


def h_merger_ask(qs, body):
    return merger.ask(body["person"], body["question"])


def h_merger_reset(qs, body):
    merger.reset()
    return {"ok": True}


ROUTES = [
    ("GET", "/api/merger", h_merger), ("POST", "/api/merger/phase", h_merger_phase), ("POST", "/api/merger/event", h_merger_event),
    ("POST", "/api/merger/conflicts/{}/resolve", h_merger_resolve), ("POST", "/api/merger/fuse/{}", h_merger_fuse),
    ("GET", "/api/merger/access", h_merger_access), ("POST", "/api/merger/reset", h_merger_reset), ("POST", "/api/merger/ask", h_merger_ask), ("GET", "/api/triggerware/conflicts", h_tw_rows),
    ("POST", "/api/merger/requests", h_xreq), ("POST", "/api/merger/requests/{}/grant", h_xgrant),
    ("POST", "/api/merger/requests/{}/deny", h_xdeny), ("POST", "/api/merger/requests/{}/revoke", h_xrevoke),
    ("GET", "/api/org", h_org), ("POST", "/api/ask", h_ask), ("GET", "/api/status", h_status),
    ("GET", "/api/conflicts", h_conflicts), ("POST", "/api/conflicts/{}/resolve", h_resolve),
    ("POST", "/api/conflicts/{}/nudge", h_nudge),
    ("POST", "/api/tasks/{}/move", h_tasks_move), ("POST", "/api/tasks/balance", h_balance),
    ("GET", "/api/governance", h_governance), ("POST", "/api/requests", h_request),
    ("POST", "/api/requests/{}/grant", h_grant), ("POST", "/api/requests/{}/deny", h_deny),
    ("POST", "/api/grants/{}/revoke", h_revoke), ("POST", "/api/demo/event", h_demo_event),
    ("GET", "/api/health", h_health), ("POST", "/api/prs", h_pr), ("GET", "/api/prs", h_prs), ("POST", "/api/reset", h_reset),
]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        if method == "GET" and url.path in ("/", "/index.html"):
            page = (b"<!doctype html><html lang=en><head><meta charset=utf-8>"
                    b"<meta name=viewport content='width=device-width, initial-scale=1, viewport-fit=cover'></head><body>"
                    + WEB.read_bytes() + b"</body></html>")
            return self._send(200, page, "text/html; charset=utf-8")
        qs = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        body = {}
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        parts = url.path.strip("/").split("/")
        for m, pattern, fn in ROUTES:
            pp = pattern.strip("/").split("/")
            if m != method or len(pp) != len(parts):
                continue
            params = []
            if all(a == b or (a == "{}" and params.append(b) is None) for a, b in zip(pp, parts)):
                try:
                    person = body.get("person") or qs.get("person")
                    if person and person not in P and not (url.path.startswith("/api/merger") and person in merger.P):
                        return self._send(400, {"error": "Unknown person"})
                    return self._send(200, fn(qs, body, *params))
                except Exception as e:
                    traceback.print_exc()
                    return self._send(500, {"error": str(e)})
        self._send(404, {"error": "Not found"})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(json.dumps(boot(), indent=2))
    print(f"Northgate Brain on http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
