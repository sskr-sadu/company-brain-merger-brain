---
company: northgate
scope: org/dept/engineering/team/billing
source_type: chat
authority: 1
date: 2026-11-04
author: "#billing-eng export"
sensitivity: internal
channel: "#billing-eng"
---

# #billing-eng (Slack export, Nov 4)

Priya Raman (09:41): Saw Platform's Identity v2 decision. Switching user IDs to UUIDs in the Q1 train will break the nightly invoice batch.
Priya Raman (09:44): I'm looking into it now and pulling the UUID migration estimate together today. Will sync with Wei tomorrow.
Billing engineer (09:52): Our invoice job casts user_id to int in three places, so yes, it fails hard.
