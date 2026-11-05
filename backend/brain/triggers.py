"""Triggers: SQL queries over the brain whose result changes fire the remind step.

Three named triggers watch the `conflicts` table. After every ingest the detectors run, then each trigger's
query is evaluated and compared with its last result (a delta of rows added and removed, the same shape as a
Triggerware TriggerDelta). New rows notify their owners.

Triggerware: if the `triggerware` Python SDK is installed and a server answers on TRIGGERWARE_URL
(default localhost:5221), the bridge connects and registers the same triggers there. The SDK's README does not
yet document how a table is backed by external data, so the bridge reports what it could register and the
local engine keeps firing either way. Ask the organizers for their table/trigger example and fill it in
`TriggerwareBridge.register`.
"""
import asyncio
import json
import os

from . import access, conflicts, db

TRIGGERS = {
    "drift_findings": "SELECT id FROM conflicts WHERE kind='drift' AND status='open'",
    "clashes": "SELECT id FROM conflicts WHERE kind='team_clash' AND status='open'",
    "contract_breaches": "SELECT id FROM conflicts WHERE kind='contract_breach' AND status='open'",
    "pr_checks": "SELECT id FROM conflicts WHERE kind='pr' AND status='open'",
}
# merger brain triggers (deal layer); they fire from merger.py and register with Triggerware the same way
MERGER_TRIGGERS = {
    "plan_task_conflicts": "SELECT id FROM merger_conflicts WHERE status='open'",
    "gate_readiness": "SELECT k FROM merger_state WHERE k='phase'",
    "unit_fusion_ready": "SELECT pair FROM fusion",
}


class TriggerwareBridge:
    """Registers the brain's triggers with a Triggerware server (tw2-sdks Python client).

    1. Creates a Triggerware table `brain_conflicts` from a prompt: Triggerware generates the table code that reads
       the brain's open conflicts (company and merger) from GET {BRAIN_URL}/api/triggerware/conflicts.
    2. Creates one trigger per brain trigger: SQL over `brain_conflicts`, with a description and a schedule.
    3. Watches each trigger; every delta Triggerware pushes becomes a notification in the brain.
    Without the SDK or a server, the local engine below fires the same triggers with the same delta semantics.
    """

    TABLE = "brain_conflicts"

    def __init__(self):
        self.status = "not installed"
        self.registered = []
        self.deltas = []
        try:
            import triggerware  # noqa: F401
            self.sdk = True
        except Exception:
            self.sdk = False

    def specs(self):
        t = self.TABLE
        out = {}
        for kind, name, desc in (("drift", "drift_findings", "A member's private work drifts from a team SOP"),
                                 ("team_clash", "clashes", "Two sibling teams' decisions collide"),
                                 ("contract_breach", "contract_breaches", "A commitment between departments is broken"),
                                 ("pr", "pr_checks", "A pull request breaks an SOP, policy, contract or the plan"),
                                 ("merger", "plan_task_conflicts", "An event in either company brain breaks a merger plan task")):
            out[name] = {"description": desc, "sql": f"SELECT id, title FROM {t} WHERE kind = '{kind}' AND status = 'open'"}
        return out

    def register(self):
        if not self.sdk:
            self.status = "SDK not installed (pip install ./tw2-sdks/python); using the local trigger engine"
            return self.status
        url = os.environ.get("TRIGGERWARE_URL", "localhost:5221")
        brain = os.environ.get("BRAIN_URL", "http://localhost:8000")
        sched = os.environ.get("TRIGGERWARE_SCHEDULE", "*/1 * * * *")

        async def go():
            from triggerware import TriggerwareClient
            client = await TriggerwareClient.connect_tcp(url)
            await client.system.health()
            tables = await client.tables.list() or []
            if self.TABLE not in tables:
                await client.tables.create(prompt=(
                    f"Create a table named {self.TABLE} with columns id (text), kind (text), status (text), title (text), "
                    f"scope (text), created (text). Its rows come from an HTTP GET to {brain}/api/triggerware/conflicts, "
                    "which returns a JSON array of objects with exactly those keys."))
            existing = set(await client.triggers.list() or [])
            for name, spec in self.specs().items():
                if name not in existing:
                    await client.triggers.create(name, description=spec["description"], sql=spec["sql"], schedule=sched, enabled=True)
                self.registered.append(name)

                async def on_delta(delta, _name=name):
                    self.deltas.append({"trigger": _name, "delta": delta})
                    for row in (delta.get("added") or []) if isinstance(delta, dict) else []:
                        rid = row.get("id") if isinstance(row, dict) else row[0]
                        db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
                             ("triggerware", f"{_name}: new row", rid, access.TODAY))
                try:
                    await client.triggers.watch(name, on_delta)
                except Exception:
                    pass
            return True

        try:
            asyncio.run(asyncio.wait_for(go(), timeout=float(os.environ.get("TRIGGERWARE_TIMEOUT", "8"))))
            self.status = f"connected to {url}; table {self.TABLE}; triggers: {', '.join(self.registered)}"
        except Exception as e:
            self.status = f"SDK installed but Triggerware at {url} not reachable ({e.__class__.__name__}); using the local trigger engine"
        return self.status


def rows_for_triggerware():
    """The rows behind the Triggerware table `brain_conflicts`: every company and merger conflict."""
    rows = [{"id": r["id"], "kind": r["kind"], "status": r["status"], "title": r["title"], "scope": r["scope"], "created": r["created_at"] if "created_at" in r.keys() else ""}
            for r in db.q("SELECT * FROM conflicts")]
    try:
        rows += [{"id": r["id"], "kind": "merger", "status": r["status"], "title": r["title"], "scope": "deal", "created": r["created"] or ""}
                 for r in db.q("SELECT * FROM merger_conflicts")]
    except Exception:
        pass
    return rows


BRIDGE = TriggerwareBridge()


def run():
    """Run detectors, evaluate every trigger, and notify on rows added since the last run."""
    conflicts.run_detectors()
    fired = {}
    for name, sql in TRIGGERS.items():
        rows = {r["id"] for r in db.q(sql)}
        prev = db.q("SELECT rows FROM trigger_state WHERE name=?", (name,))
        before = set(json.loads(prev[0]["rows"])) if prev else set()
        added, removed = rows - before, before - rows
        db.x("INSERT OR REPLACE INTO trigger_state VALUES (?,?)", (name, json.dumps(sorted(rows))))
        for cid in added:
            c = db.q("SELECT * FROM conflicts WHERE id=?", (cid,))[0]
            for p in json.loads(c["notify"]):
                db.x("INSERT INTO notifications (to_person, text, ref, created_at) VALUES (?,?,?,?)",
                     (p, c["title"], cid, access.TODAY))
            db.audit("trigger:" + name, "fired", {"conflict": cid, "notify": json.loads(c["notify"])}, access.TODAY)
        if added or removed:
            fired[name] = {"added": sorted(added), "removed": sorted(removed)}
    return fired
