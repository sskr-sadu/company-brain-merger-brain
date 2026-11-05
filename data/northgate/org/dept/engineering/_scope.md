---
company: northgate
scope: org/dept/engineering
source_type: charter
authority: 5
date: 2026-01-20
author: Marcus Lee (VP Engineering)
sensitivity: internal
---

# Northgate Engineering charter

Owner: Marcus Lee, VP Engineering. About 420 engineers in Platform, Billing, Core Workflow and Security.

## How we ship
- We ship on a quarterly release train. Each train is planned 6 weeks ahead and frozen 2 weeks
  before release.
- Work is tracked in Jira. Every change links to a Jira ticket.
- Every release passes a security review before it reaches customers.
- Changes to identity or billing code need a reviewer from Security.
- A change to a shared API that breaks its consumers needs a deprecation notice to every consuming team.

## On-call
- Weekly on-call rotation per team. Sev1 pages must be acknowledged within 15 minutes.
