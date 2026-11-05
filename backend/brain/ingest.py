"""Ingest: files -> sources -> typed items with exact source spans.

Steps per file: hash, read front-matter, redact secrets, scan for instructions aimed at the AI (quarantine),
split into items, tag subjects and entities, store. Extraction is deterministic so every quote is an exact
substring of its source; an optional Claude pass can refine item types (see llm.py) without changing spans.
"""
import hashlib
import json
import re

from . import db

COMPANY = db.ORG["company"]
DIR_TO_SCOPE = {v["dir"]: k for k, v in db.ORG["scopes"].items()}
NAME_TO_PERSON = {p["name"]: pid for pid, p in db.ORG["people"].items()}

INJECTION = re.compile(
    r"(ignore (all )?(previous|prior) instructions|disregard your rules|you are now in [a-z ]*mode|"
    r"note to any ai|^\s*system\s*:|reveal (all )?restricted)", re.I | re.M)
SECRETS = [
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"), "[redacted key]"),
    (re.compile(r"(?i)(password|passwd|secret)\s*[:=]\s*\S+"), r"\1: [redacted]"),
    (re.compile(r"\b\+?1?[ -.]?\(?\d{3}\)?[ -.]\d{3}[ -.]\d{4}\b"), "[redacted phone]"),
]

SUBJECTS = {
    "release process": r"release train|ship(s|ped|ping)?\b|deploy|production|sev1|continuous deploy",
    "spending approval": r"approv\w* .*\$|\$[\d,]+.*approv|purchase",
    "user id format": r"user_id|user id|uuid|integer ids?",
    "sso": r"\bsso\b|saml|scim|single sign-on",
    "pricing": r"price|per user per month|discount",
    "remote work": r"\boffice\b|remote",
    "time off": r"time off|\bpto\b|parental leave",
    "churn": r"churn",
    "crm": r"salesforce|hubspot|\bcrm\b",
    "payment retries": r"retr(y|ies)",
    "security review": r"security review",
    "hiring": r"interview|hiring|candidate",
}
ENTITIES = {
    "Identity API": ("e", r"identity api|identity service|identity v2"),
    "Billing service": ("e", r"billing service|invoice job|invoices? (and|table)|billing database"),
    "Release train": ("e", r"release train|\btrain\b"),
    "Payment processor": ("e", r"payment processor"),
    "Workflow API": ("e", r"workflow api"),
    "Audit log": ("e", r"audit log"),
    "Salesforce": ("e", r"salesforce"),
    "Acme Health": ("e", r"acme health"),
    "Brightline Insurance": ("e", r"brightline"),
    "Corvid Labs": ("e", r"corvid labs"),
}
for _name, _pid in NAME_TO_PERSON.items():
    ENTITIES[_name] = ("p", re.escape(_name))
TICKET = re.compile(r"\b(PLAT|BILL)-\d+\b")
HARD = re.compile(r"\b(must|needs? approval|never|only|required|unless|no release|nothing ships|at least|"
                  r"must-have|every release|locked|retired)\b", re.I)
TYPE_BY_SOURCE = {
    "policy": "policy", "charter": "policy", "decision_log": "decision", "goal": "goal", "contract": "contract",
    "procedure": "procedure", "architecture": "fact", "metric_glossary": "metric", "crm_export": "fact",
    "kpi_table": "fact", "meeting_notes": "fact", "email": "fact", "git_log": "decision",
    "ticket_export": "task", "chat": "fact", "incident": "fact", "org_chart": "fact", "strategy": "goal",
}
PUBLISHED_TYPES = {"policy", "charter", "contract", "org_chart", "metric_glossary", "strategy"}


def parse_front_matter(text):
    if not text.startswith("---\n"):
        return {}, text, 0
    end = text.index("\n---\n", 4)
    meta = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    body_start = end + 5
    return meta, text[body_start:], body_start


def scope_for(path):
    rel = path.parent.relative_to(db.DATA / COMPANY).as_posix()
    while rel and rel not in DIR_TO_SCOPE:
        rel = rel.rsplit("/", 1)[0] if "/" in rel else ""
    return DIR_TO_SCOPE.get(rel, "org")


def norm(text):
    return re.sub(r"\s+", " ", text).strip()


def tag(text, table):
    return [k for k, v in table.items() if re.search(v if isinstance(v, str) else v[1], text, re.I)]


def _join_wrapped(body):
    """Yield (line, start) with indented continuation lines folded into the line they continue.
    The yielded line is the exact source span, so it may contain a newline and indentation."""
    lines = body.splitlines(keepends=True)
    pos, i = 0, 0
    while i < len(lines):
        start, span = pos, lines[i]
        pos += len(lines[i])
        i += 1
        while i < len(lines) and re.match(r"^ {2,}\S", lines[i]) and span.strip() and not span.lstrip().startswith("|"):
            span += lines[i]
            pos += len(lines[i])
            i += 1
        yield span, start


def split_items(body):
    """Yield (clean_text, quote, start) where quote is an exact substring of body starting at start."""
    header = None
    for raw, start in _join_wrapped(body):
        line = raw.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("---"):
            header = None if not s.startswith("|") else header
            continue
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if header is None:
                header = cells
                continue
            quote = s.strip("|").strip()
            text = " · ".join(c for c in cells if c)
            yield text, quote, start + line.index(quote)
            continue
        header = None
        m = re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)
        content = line[m.end():] if m else line.strip()
        offset = start + (m.end() if m else line.index(content))
        if m or len(content) < 220:
            yield content, content, offset
        else:
            for sm in re.finditer(r"[^.!?]+[.!?]", content):
                sent = sm.group(0).strip()
                yield sent, sent, offset + sm.start() + (len(sm.group(0)) - len(sm.group(0).lstrip()))


def parse_contracts(source_id, scope, body):
    out = []
    for block in re.split(r"\n## ", "\n" + body)[1:]:
        title = block.splitlines()[0].strip()
        block = re.sub(r"\n {2,}", " ", block)
        fields = dict(re.findall(r"^- ([A-Za-z-]+):\s*(.+)$", block, re.M))
        def side(v):
            if not v:
                return None, None
            owner = next((pid for n, pid in NAME_TO_PERSON.items() if n in v), None)
            name = v.split("(")[0].strip()
            sc = {"Engineering": "org/eng", "Sales": "org/sales", "Platform team": "org/eng/platform",
                  "Billing team": "org/eng/billing", "People": "org/people"}.get(name, name)
            return sc, owner
        prov, prov_owner = side(fields.get("Provider", "").split(".")[0])
        cons, cons_owner = side(fields.get("Consumer", "").split(".")[0])
        must = fields.get("Must-have", "")
        date = re.search(r"\d{4}-\d{2}-\d{2}", must)
        subj = tag(title + " " + must, SUBJECTS)
        out.append({"id": f"{source_id}#{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}", "scope": scope,
                    "title": title, "provider": prov, "consumer": cons, "provider_owner": prov_owner,
                    "consumer_owner": cons_owner, "must_have": must, "must_have_date": date.group(0) if date else None,
                    "subject": ",".join(subj), "source_id": source_id})
    return out


def ingest_file(path):
    raw = path.read_text()
    sha = hashlib.sha256(raw.encode()).hexdigest()
    meta, body, _ = parse_front_matter(raw)
    for rx, rep in SECRETS:
        body = rx.sub(rep, body)
    rel = path.relative_to(db.DATA).as_posix()
    scope = scope_for(path)
    st = meta.get("source_type", "meeting_notes")
    sens = meta.get("sensitivity", "internal")
    status = meta.get("status", "current")
    inj = INJECTION.search(body)
    db.x("INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
         (rel, rel, scope, st, int(meta.get("authority", 2)), meta.get("date"), meta.get("author"), sens, status,
          sha, 1 if inj else 0, inj.group(0) if inj else None, body))
    db.x("DELETE FROM items WHERE source_id=?", (rel,))
    if inj:
        return {"path": rel, "quarantined": inj.group(0)}
    kind = db.ORG["scopes"][scope]["kind"]
    owner = db.ORG["scopes"][scope]["owner"]
    publish = int((st in PUBLISHED_TYPES and kind in ("org", "dept") or meta.get("publish") == "down") and sens == "internal")
    n = 0
    for i, (text, quote, start) in enumerate(split_items(body)):
        if len(text) < 8:
            continue
        assert body[start:start + len(quote)] == quote, (rel, quote)
        typ = TYPE_BY_SOURCE.get(st, "fact")
        if re.search(r"^decision:|^- decision:", text, re.I) or text.lower().startswith("decision"):
            typ = "decision"
        if TICKET.search(text) and st == "ticket_export":
            typ = "task"
        date = re.search(r"\b(20\d\d-\d\d-\d\d)\b", text)
        ents = tag(text, ENTITIES) + sorted(set(m.group(0) for m in TICKET.finditer(text)))
        iid = f"{rel}:{i}"
        db.x("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (iid, rel, scope, typ, "hard" if HARD.search(text) else "soft", quote, start, start + len(quote),
              date.group(1) if date and st in ("git_log", "decision_log") else meta.get("date"), sens, status,
              publish, int(meta.get("authority", 2)), json.dumps(tag(text, SUBJECTS)), json.dumps(ents), owner))
        db.x("INSERT INTO items_fts (id, text) VALUES (?,?)", (iid, norm(text)))
        n += 1
    if st == "contract":
        for c in parse_contracts(rel, scope, body):
            db.x("INSERT OR REPLACE INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(c.values()))
    return {"path": rel, "items": n}


def ingest_all():
    db.reset()
    report = [ingest_file(p) for p in sorted((db.DATA / COMPANY).rglob("*.md"))]
    plan = json.loads((db.DATA / COMPANY / "_plan.json").read_text())
    for t in plan["tasks"]:
        db.x("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
             (t["id"], t["who"], t["title"], t["hours"], t["day"], t["priority"], t.get("critical"),
              t.get("off_plan"), t.get("feeds"), t.get("needs")))
    for m in plan["milestones"]:
        db.x("INSERT INTO milestones VALUES (?,?,?,?,?,?)",
             (m["scope"], m["date"], m["label"], m["progress"], m["state"], int(m["risk"])))
    for c in plan.get("completed", []):
        db.x("INSERT INTO completed VALUES (?,?,?,?,?)", (c["who"], c["date"], c.get("time"), c["title"], c["ref"]))
    db.audit("system", "ingest_all", {"files": len(report)}, db.ORG["today"])
    return report


def rebuild_fts():
    db.x("DELETE FROM items_fts")
    for r in db.q("SELECT id, text FROM items"):
        db.x("INSERT INTO items_fts (id, text) VALUES (?,?)", (r["id"], norm(r["text"])))
