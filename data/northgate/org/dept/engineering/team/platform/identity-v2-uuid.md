---
company: northgate
scope: org/dept/engineering/team/platform
source_type: decision_log
authority: 4
date: 2026-11-02
author: Wei Zhang (Platform lead)
sensitivity: internal
---

# Platform design decision: Identity API v2 uses UUIDs

- Decision: from the Q1 2027 release train, the Identity API returns `user_id` as a UUID string
  instead of an integer. The integer IDs are retired in the same release.
- Why: SSO and SCIM provisioning need globally unique IDs across customer directories.
- Reviewed by: Platform team and Security.
