---
company: northgate
scope: org/dept/engineering
source_type: architecture
authority: 3
date: 2026-05-11
author: Platform team
sensitivity: internal
---

# Northgate system architecture (summary)

| System | Owner team | Notes |
| --- | --- | --- |
| Workflow API | Core Workflow | Public REST API, versioned per release train |
| Billing service | Billing | Invoices and payment retries; retries go through a queue |
| Identity service | Platform | Today: username and password; SSO planned for Q1 2027 |
| Audit log | Security | Append-only store required by healthcare customers |
