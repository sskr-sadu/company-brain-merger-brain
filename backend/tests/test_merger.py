"""Merger brain tests: clash register, access between companies by phase, negotiation and plan versions, fusion."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from brain import ingest, merger  # noqa: E402


class Merger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ingest.ingest_all()
        merger.reset()

    @classmethod
    def tearDownClass(cls):
        merger.reset()

    def test_01_register_cites_both_sides(self):
        r = merger.register()
        self.assertEqual(len(r["clashes"]), 11)
        for c in r["clashes"]:
            for side in ("ng", "pp"):
                if c[side] and not c["restricted"]:
                    self.assertTrue(c[side]["quote"], (c["id"], side))
        self.assertTrue(all(d["ng"]["quote"] and d["pp"]["quote"] for d in r["decoys"]))  # decoys checked, not flagged

    def test_02_pricing_never_quoted(self):
        c = next(c for c in merger.register()["clashes"] if c["id"] == "C10")
        self.assertIsNone(c["ng"]["quote"])
        self.assertIsNone(c["pp"]["quote"])

    def test_10_access_opens_by_phase(self):
        a = lambda ph: merger.cross_access("priya", "pp:org/eng/billing", "area", ph)
        self.assertFalse(a("pre")["allowed"])
        self.assertFalse(a("q1")["allowed"])
        self.assertEqual(a("q1")["approvers"], ["leo"])
        self.assertTrue(merger.cross_access("priya", "pp:org/eng/billing", "team_card", "q1")["allowed"])
        self.assertTrue(a("q2")["allowed"])

    def test_11_restricted_and_drafts_never_cross(self):
        for ph in merger.PHASES:
            self.assertFalse(merger.cross_access("tom", "pp:org/sales", "restricted", ph)["allowed"])
            self.assertFalse(merger.cross_access("marcus", "pp:org/eng", "draft", ph)["allowed"])

    def test_12_mirror_ceiling(self):
        r = merger.cross_access("tom", "pp:org/sales/midmarket", "area", "q3")
        self.assertFalse(r["allowed"])
        self.assertIn("not grantable", r["why"])

    def test_13_owning_side_grants_cross_company_access(self):
        rid = merger.requests()[0]["id"]                      # seeded: Priya asks for Pulsepoint Billing
        self.assertIn("error", merger.decide(rid, "wei"))      # not the owning side
        self.assertTrue(merger.decide(rid, "leo")["ok"])
        self.assertTrue(merger.cross_access("priya", "pp:org/eng/billing", "area", "q1")["allowed"])
        self.assertIn("error", merger.request("tom", "pp:org/sales/midmarket", "x"))  # beyond his matching position

    def test_14_ask_respects_phase_and_level(self):
        r = merger.ask("tom", "What is in the Pulsepoint Mid-market pipeline?", "q1")
        self.assertEqual(r["status"], "blocked")
        self.assertFalse(r["cites"])
        r = merger.ask("tom", "How does Pulsepoint deploy?", "q1")
        self.assertTrue(all(merger.can_read_file("tom", c["file"], "q1") for c in r["cites"] if "/" in c["file"]))
        self.assertEqual(merger.ask("tom", "How does Pulsepoint deploy?", "pre")["cites"] and
                         [c for c in merger.ask("tom", "How does Pulsepoint deploy?", "pre")["cites"] if c["file"].startswith("pulsepoint")], [])

    def test_15_lead_sees_only_his_pair(self):
        files = {c["file"] for c in merger.ask("priya", "What are our joint tasks this quarter?", "q1")["cites"]}
        self.assertFalse([f for f in files if "P1" in f or "P4" in f])

    def test_20_event_breaks_plan_and_blocks_gate(self):
        self.assertEqual(merger.check_event(), ["M-T-07"])
        self.assertFalse(merger.gate("q1")["ok"])
        self.assertEqual(merger.conflicts("tom"), [])
        self.assertEqual(len(merger.conflicts("aisha")), 1)

    def test_21_choice_writes_plan_v2(self):
        r = merger.resolve("M-T-07", "Release train for healthcare customers only", "aisha")
        self.assertEqual(r["version"], 2)
        self.assertTrue((merger.db.DATA / "deal" / "plan-v2.md").exists())
        self.assertTrue(merger.gate("q1")["ok"])

    def test_30_fusion_waits_for_checks_and_keeps_origin(self):
        self.assertIn("error", merger.fuse("P2", ph="q1"))
        merger.set_phase("q3")
        r = merger.fuse("P2")
        self.assertEqual(r["fused_id"], "fz:org/eng/billing")
        self.assertEqual(set(r["aliases"]), {"ng:org/eng/billing", "pp:org/eng/billing"})
        self.assertEqual({i["origin"] for i in r["items"]}, {"ng", "pp"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
