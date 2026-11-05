---
company: northgate
scope: org/dept/engineering
source_type: contract
authority: 4
date: 2026-03-02
author: Marcus Lee (VP Engineering)
sensitivity: internal
---

# Contracts between Engineering teams

## Identity API for Billing
- Provider: Platform team (owner Wei Zhang)
- Consumer: Billing team (owner Priya Raman)
- Promise: the Identity API that Billing uses to map users to accounts.
- Must-have: breaking changes to the API are announced at least one release train ahead, and the
  old format keeps working for one full train after the new one ships.
- Nice-to-have: a sandbox with the new format two weeks before the freeze.
