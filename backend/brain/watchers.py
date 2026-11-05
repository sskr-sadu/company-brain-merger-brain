"""Who's on it: scan Slack and email in the brain for people discussing a conflict, and tell whether someone
is handling it, has only noticed it, or nobody has picked it up.

A message counts as about the conflict when it hits at least two of the conflict's keywords (its systems,
subjects and ticket ids). It counts as handling when it also states intent ("looking into it", "I'll come
back by Friday"). The viewer sees the quote only if they may read the channel it came from; otherwise only
who, where and when.
"""
import json
import re

from . import access, db, ingest

INTENT = re.compile(r"\b(looking into|i'?m on it|on it\b|pulling [^.]* together|will (sync|come back|follow up|look|check)|"
                    r"investigating|i'?ll (handle|take|look|follow|come back|check)|working on)", re.I)
CHAT_LINE = re.compile(r"^(?P<name>[A-Z][a-z]+ [A-Z][a-z]+) \((?P<time>\d\d:\d\d)\): (?P<msg>.+)$", re.M)
NAME_TO_PID = {p["name"]: pid for pid, p in db.ORG["people"].items()}


def _keywords(conflict):
    text = " ".join(e[1] for e in json.loads(conflict["evidence"])) + " " + conflict["title"]
    pats = [ingest.ENTITIES[e][1] for e in ingest.tag(text, ingest.ENTITIES) if ingest.ENTITIES[e][0] == "e"]
    pats += [ingest.SUBJECTS[s] for s in ingest.tag(text, ingest.SUBJECTS)]
    pats += [re.escape(t) for t in set(ingest.TICKET.findall(text))]
    return pats


def _messages():
    """Every Slack message and email in the brain, with author, channel, date and an exact quote."""
    out = []
    for s in db.q("SELECT * FROM sources WHERE source_type IN ('chat', 'email') AND quarantined = 0"):
        head = re.search(r"^# (.+)$", s["body"], re.M)
        chan = re.search(r"#[\w-]+", head.group(1)) if head else None
        if s["source_type"] == "chat":
            for m in CHAT_LINE.finditer(s["body"]):
                if m.group("name") in NAME_TO_PID:
                    out.append({"who": NAME_TO_PID[m.group("name")], "channel": chan.group(0) if chan else "Slack",
                                "when": f"{s['date']} {m.group('time')}", "text": m.group("msg"), "source": s})
        else:
            author = next((pid for n, pid in NAME_TO_PID.items() if n in (s["author"] or "")), None)
            if author:
                body = re.sub(r"\s+", " ", s["body"].split("\n\n", 2)[-1])
                out.append({"who": author, "channel": "email", "when": s["date"], "text": body, "source": s})
    return out


def watch(conflict, viewer):
    if conflict["kind"] == "drift":       # private reminders are not tracked in team channels
        return {"state": "private", "people": []}
    pats = _keywords(conflict)
    since = max(e for e in [conflict["created_at"]] + [s["date"] for s in db.q(
        "SELECT date FROM sources WHERE id IN ({})".format(",".join("?" * 2)),
        [e[2] for e in json.loads(conflict["evidence"])][:2]) if s["date"]])
    found, threads = {}, set()
    for m in sorted(_messages(), key=lambda m: m["when"]):
        if m["when"][:10] < since:
            continue
        hits = sum(1 for p in pats if re.search(p, m["text"], re.I))
        thread = (m["who"], m["channel"], m["when"][:10])
        if hits >= 2:
            threads.add(thread)
        elif not (thread in threads and INTENT.search(m["text"])):   # a same-day follow-up in the same thread counts
            continue
        intent = INTENT.search(m["text"])
        prev = found.get(m["who"])
        if prev and (prev["handling"] or not intent):
            continue
        sentence = next((x.strip() for x in re.split(r"(?<=[.!?])\s+", m["text"]) if INTENT.search(x)), m["text"])
        can = access.can_read_scope(viewer, m["source"]["scope"])
        found[m["who"]] = {"who": m["who"], "name": db.ORG["people"][m["who"]]["name"], "channel": m["channel"],
                           "where": db.ORG["scopes"][m["source"]["scope"]]["name"], "when": m["when"],
                           "handling": bool(intent), "quote": sentence[:240] if can else None,
                           "source": m["source"]["path"] if can else None}
    people = sorted(found.values(), key=lambda x: (not x["handling"], x["when"]))
    state = "handling" if any(p["handling"] for p in people) else "aware" if people else "nobody"
    owners = json.loads(conflict["notify"])
    return {"state": state, "people": people,
            "nudge": None if state == "handling" else owners[0]}
