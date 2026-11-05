# Company Brain → Merger Brain

**Company Brain:** a memory for each team (org → department → team → member) with top-down access. It answers with cited sources, plans each team's work by day and week, and catches conflicts: drift from SOPs, clashes between teams, broken contracts between departments, and pull requests that go off-plan. Each conflict gets three resolution plans and a check of who is already handling it.

**Merger Brain:** extends it to an acquisition (Northgate acquires Pulsepoint). It compares both companies on Day 0, builds a one-year plan in phases (Stabilize → Align → Integrate → Fuse) down to each pair of teams, and gives cross-company access by phase and job level. When a change in either company breaks the plan, it negotiates a fix and writes a new plan version. Finally it fuses the two brains unit by unit.

- **Run:** `python3 backend/server.py`, then open http://localhost:8000. Switch between **Northgate** and **Northgate × Pulsepoint** at the top of the sidebar.
- **Tests:** `python3 -m unittest discover -s backend/tests` (37 tests)
- **Triggerware and API details:** [backend/README.md](backend/README.md)
