---
company: northgate
scope: org/dept/engineering/team/billing
source_type: architecture
authority: 3
date: 2026-09-18
author: Priya Raman (Billing lead)
sensitivity: internal
---

# How Billing uses the Identity API

- The `invoices` and `payment_methods` tables are keyed on the integer `user_id` returned by the
  Identity API (`GET /v1/users/{user_id}`).
- The invoice job parses `user_id` as an integer; a non-numeric value fails the whole nightly batch.
- Migrating Billing to another ID format needs about 6 weeks: a schema change, a backfill of 4 years
  of invoices, and a finance sign-off on the reconciliation.
