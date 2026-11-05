"""Demo-gate tests: the access table and the three Northgate scenarios from the build plan.
Run: python3 -m unittest discover -s backend/tests -v
"""
import json
import pathlib
import shutil
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from brain import access, ask, conflicts, db, ingest, planner, triggers  # noqa: E402
import server  # noqa: E402


def clean_generated():
    for d in (db.DATA / "northgate").rglob("decisions"):
        shutil.rmtree(d)
    for f in (db.DATA / "northgate").rglob("sso-slip.md"):
        f.unlink()


class Brain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clean_generated()
        ingest.ingest_all()
        triggers.run()

    @classmethod
    def tearDownClass(cls):
        clean_generated()

    # ---- access table ----------------------------------------------------------------------------
    def test_01_ceo_reads_billing(self):
        self.assertEqual(ask.ask("dana", "How does Billing use the Identity API?")["status"], "ok")

    def test_02_vp_reads_his_department(self):
        self.assertEqual(ask.ask("marcus", "How does Billing use the Identity API?")["status"], "ok")

    def test_03_vp_blocked_from_sales_pricing(self):
        r = ask.ask("marcus", "What does Acme Health pay us?")
        self.assertEqual(r["status"], "blocked")
        self.assertEqual(set(r["blocked"]["approvers"]), {"elena", "dana"})
        self.assertNotIn("$120", json.dumps(r))

    def test_04_lead_blocked_from_sibling_team(self):
        r = ask.ask("priya", "What is Platform changing in the Identity API?")
        self.assertEqual(r["status"], "blocked")
        self.assertIn("marcus", r["blocked"]["approvers"])
        self.assertIn("wei", r["blocked"]["approvers"])

    def test_05_grant_opens_module_and_is_logged(self):
        server.h_request({}, {"person": "priya", "scope": "org/eng/platform", "why": "UUID plan"})
        rid = db.q("SELECT id FROM requests WHERE who='priya' ORDER BY id DESC LIMIT 1")[0]["id"]
        self.assertTrue(server.h_grant({}, {"person": "marcus"}, rid)["ok"])
        r = ask.ask("priya", "What is Platform changing in the Identity API?")
        self.assertEqual(r["status"], "ok")
        self.assertIn("grant from Marcus Lee", r["access_note"])
        self.assertTrue(db.q("SELECT 1 FROM audit WHERE actor='priya' AND action='grant_use'"))
        db.x("UPDATE grants SET revoked=1")

    def test_06_member_reads_own_team(self):
        r = ask.ask("tom", "Where are we on SSO?")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("platform" in c["file"] for c in r["cites"]))

    def test_07_member_reads_published_handbook(self):
        r = ask.ask("tom", "Can I approve a $15K tool purchase?")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(any("employee-handbook" in c["file"] for c in r["cites"]))

    def test_08_restricted_never_reaches_a_member(self):
        where, args = access.item_filter_sql("tom")
        self.assertFalse(db.q(f"SELECT 1 FROM items i WHERE {where} AND i.sensitivity != 'internal'", args))

    def test_09_private_draft_hidden_from_everyone_else(self):
        for p in ("dana", "marcus", "wei"):
            where, args = access.item_filter_sql(p)
            self.assertFalse(db.q(f"SELECT 1 FROM items i WHERE {where} AND i.status='draft'", args), p)

    def test_10_injected_file_quarantined(self):
        self.assertEqual(db.q("SELECT quarantined FROM sources WHERE path LIKE '%vendor-faq.md'")[0]["quarantined"], 1)

    def test_11_every_citation_matches_its_source(self):
        r = ask.ask("dana", "Where are we on SSO?")
        self.assertTrue(all(c["verified"] for c in r["cites"]))

    # ---- scenarios -------------------------------------------------------------------------------
    def test_20_scenario1_member_drift_private(self):
        mine = [c for c in conflicts.visible("tom") if c["trigger"] == "drift_findings"]
        self.assertEqual(len(mine), 1)
        self.assertFalse([c for c in conflicts.visible("wei") if c["trigger"] == "drift_findings"])

    def test_21_scenario4_sibling_teams_clash(self):
        c = [c for c in conflicts.visible("priya") if c["trigger"] == "clashes"]
        self.assertEqual(len(c), 1)
        self.assertIn("Identity API", c[0]["ev"][0][1])
        self.assertTrue([x for x in conflicts.visible("marcus") if x["trigger"] == "clashes"])
        self.assertFalse([x for x in conflicts.visible("tom") if x["trigger"] == "clashes"])

    def test_22_scenario2_contract_breach_after_event(self):
        server.h_demo_event({}, {"name": "sso-slip"})
        c = [c for c in conflicts.visible("elena") if c["trigger"] == "contract_breaches"]
        self.assertEqual(len(c), 1)
        self.assertIn("2027-03-31", c[0]["extra"])

    def test_23_decision_writes_back_and_is_cited(self):
        cid = [c for c in conflicts.visible("wei") if c["trigger"] == "clashes"][0]["id"]
        server.h_resolve({}, {"person": "wei", "option": "Return both formats for one release train"}, cid)
        r = ask.ask("marcus", "What did we decide about the Identity API user id format?")
        self.assertIn("Return both formats", r["answer"])

    def test_24_moves_are_checked(self):
        r = planner.move("tom", "T1", "2026-11-09")
        self.assertTrue(any("critical path" in w for w in r["warn"]))
        planner.move("tom", "T1", "2026-11-04")
        self.assertIn("error", planner.move("tom", "T6", "2026-11-06"))  # not his task

    def test_25_balance_never_moves_critical_work(self):
        moves = planner.balance("wei", "org/eng/platform")["moves"]
        self.assertTrue(moves)
        self.assertFalse(any(db.q("SELECT critical FROM tasks WHERE id=?", (m["task"],))[0]["critical"] for m in moves))

    def test_26_every_conflict_has_plans_with_one_recommended(self):
        for c in conflicts.visible("dana") + conflicts.visible("tom"):
            self.assertEqual(len(c["plans"]), 3)
            self.assertEqual(sum(p["recommended"] for p in c["plans"]), 1)
            self.assertTrue(all(st["owner"] in db.ORG["people"] for p in c["plans"] for st in p["steps"]))

    def test_27_watch_finds_who_is_handling(self):
        c = [c for c in conflicts.visible("marcus") if c["trigger"] == "clashes"][0]
        self.assertEqual(c["watch"]["state"], "handling")
        self.assertEqual(c["watch"]["people"][0]["who"], "priya")
        w = [c for c in conflicts.visible("wei") if c["trigger"] == "clashes"][0]["watch"]
        self.assertIsNone(w["people"][0]["quote"])   # Wei can't read #billing-eng, so no quote

    def test_28_watch_on_contract_breach_finds_elena(self):
        server.h_demo_event({}, {"name": "sso-slip"})
        c = [c for c in conflicts.visible("elena") if c["trigger"] == "contract_breaches"][0]
        self.assertEqual(c["watch"]["state"], "handling")
        self.assertEqual(c["watch"]["people"][0]["who"], "elena")

    def test_29_choosing_a_plan_changes_tasks(self):
        cid = [c for c in conflicts.visible("tom") if c["trigger"] == "drift_findings"][0]["id"]
        db.x("UPDATE tasks SET day='2026-11-04' WHERE id='T2'")
        r = server.h_resolve({}, {"person": "tom", "option": "Put the stalled ticket back on top"}, cid)
        self.assertEqual(db.q("SELECT day FROM tasks WHERE id='T2'")[0]["day"], "2026-11-09")
        self.assertTrue(r["task_changes"])

    def test_40_pr_off_plan_and_off_policy_becomes_conflict(self):
        r = server.h_pr({}, {"demo": 4431})
        failed = {c["name"] for c in r["checks"] if not c["ok"]}
        self.assertEqual(failed, {"Linked to a ticket", "Ships through the release train", "Matches the team plan"})
        self.assertTrue(all(c["file"] for c in r["checks"] if c["name"] != "Matches the team plan"))  # each rule is cited

    def test_41_compliant_pr_passes(self):
        r = server.h_pr({}, {"demo": 4432})
        self.assertIsNone(r["conflict"])
        self.assertTrue(all(c["ok"] for c in r["checks"]))

    def test_42_breaking_api_pr_affects_consumer_team(self):
        r = server.h_pr({}, {"demo": 4433})
        self.assertTrue(any(c["name"].startswith("Contract") and not c["ok"] for c in r["checks"]))
        self.assertIn("pr-4433", [c["id"] for c in conflicts.visible("priya")])

    def test_43_board_shows_own_level_below_and_affecting_never_above(self):
        ids = lambda p: {c["id"] for c in conflicts.visible(p)}
        self.assertIn("pr-4431", ids("tom"))          # own work
        self.assertIn("pr-4431", ids("wei"))          # teammate's work
        self.assertNotIn("pr-4431", ids("priya"))     # another team's work that doesn't affect Billing
        self.assertIn("pr-4433", ids("priya"))        # another team's work that affects Billing
        self.assertNotIn("pr-4433", ids("tom"))       # his lead's work: above him
        self.assertFalse(ids("elena") & {"pr-4431", "pr-4433"})

    def test_30_audit_chain_intact(self):
        self.assertTrue(db.verify_audit()[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
