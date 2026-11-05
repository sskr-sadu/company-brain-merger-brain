---
company: northgate
scope: org/dept/engineering/team/platform
source_type: charter
authority: 5
date: 2026-10-01
author: Wei Zhang (Platform lead)
sensitivity: internal
---

# Platform team charter, Q4 2026

Owner: Wei Zhang, Platform lead. Members include Tom Okafor.

## Team goals this quarter
- Deliver SAML login (PLAT-2210) by 2027-01-15 so Enterprise SSO makes the Q1 2027 train.
  This feeds the Engineering-to-Sales SSO contract for the Acme Health renewal.
- Keep identity service uptime above 99.95%.

## Assignments
| Person | Assigned work | Due |
| --- | --- | --- |
| Tom Okafor | PLAT-2210 SAML login flow | 2027-01-15 |
| Platform team | PLAT-2214 SCIM provisioning | 2027-02-15 |
| Wei Zhang | PLAT-2230 Identity v2 UUIDs | 2027-02-01 |

## Rules (inherited from Engineering, restated)
- Nothing ships outside the release train unless it is a Sev1 fix.
