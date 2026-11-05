"""Ask: permission-filtered search, a cited answer, the knowledge graph behind it, and an access explanation.

1. Search only what the asker may read (the filter is SQL, applied before any text reaches a model).
2. Separately, check whether the best match overall sits outside the asker's access; if it clearly beats
   anything they may read, return "blocked" with the owner and who can grant access, never the content.
3. Answer from the allowed items: with Claude when a key is set (citations validated against the items),
   otherwise extractively from the top items.
"""
import json
import re

from . import access, db, llm

STOP = set("a an the is are was were be to of in on for and or what where when who why how do does did can i we "
           "our us my me it this that with at by from about as any there their they you your should could would "
           "will tell show give much many".split())
ROLE_RULES = [  # role-aware hints, e.g. a VP may approve what an engineer may not
    (re.compile(r"approv\w*.*\$|\$.*approv\w*|purchase", re.I), "spending approval"),
]


def fts_query(question):
    words = [w for w in re.findall(r"[a-z0-9$]+", question.lower()) if w not in STOP and len(w) > 1]
    words = [w.lstrip("$").replace(",", "") for w in words]
    words = [w for w in words if w]
    return " OR ".join(f'"{w}"*' if not w.isdigit() else f'"{w}"' for w in words) if words else None


def search(question, where=None, args=(), k=8):
    fq = fts_query(question)
    if not fq:
        return []
    sql = ("SELECT i.*, bm25(items_fts) AS score FROM items_fts JOIN items i ON i.id = items_fts.id "
           f"WHERE items_fts MATCH ? {'AND ' + where if where else ''} "
           "ORDER BY bm25(items_fts) - i.authority * 0.15 LIMIT ?")
    rows = db.q(sql, [fq] + list(args) + [k])
    return rows


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def cite(item):
    src = db.q("SELECT * FROM sources WHERE id=?", (item["source_id"],))[0]
    scope_name = db.ORG["scopes"][item["scope"]]["name"]
    return {"quote": norm(item["text"]), "file": item["source_id"], "scope": scope_name,
            "authority": f"{item['authority']} · {src['source_type'].replace('_', ' ')}" +
                         (" · restricted" if item["sensitivity"] == "restricted" else ""),
            "date": item["date"] or src["date"], "item_id": item["id"],
            "verified": src["body"][item["span_start"]:item["span_end"]] == item["text"]}


def graph(question, items):
    nodes = [["q", question if len(question) < 60 else question[:57] + "…", "q"]]
    edges, seen = [], set()
    name_to_pid = {p["name"]: pid for pid, p in db.ORG["people"].items()}
    for idx, it in enumerate(items):
        nid = f"k{idx}"
        label = norm(it["text"])
        nodes.append([nid, label if len(label) < 70 else label[:67] + "…", "k"])
        edges.append(["q", nid, "answers"])
        for e in json.loads(it["entities"] or "[]"):
            kind = "p" if e in name_to_pid else "e"
            eid = "x:" + e
            if eid not in seen:
                seen.add(eid)
                nodes.append([eid, e, kind])
            edges.append([nid, eid, "mentions" if kind == "e" else "names"])
        owner = db.ORG["people"][it["owner"]]["name"]
        oid = "x:" + owner
        if oid not in seen:
            seen.add(oid)
            nodes.append([oid, owner, "p"])
        edges.append([nid, oid, "owned by"])
    return {"nodes": nodes[:14], "edges": [e for e in edges if all(any(n[0] == v for n in nodes[:14]) for v in e[:2])]}


def answer_text(question, person, items):
    p = db.ORG["people"][person]
    if llm.available():
        listing = "\n".join(f"[{i}] ({db.ORG['scopes'][it['scope']]['name']}, {it['type']}) {norm(it['text'])}"
                            for i, it in enumerate(items))
        system = ("You answer questions for one employee using only the numbered passages. The employee is "
                  f"{p['name']}, {p['role']}. Answer in 1 to 3 short sentences, addressed to them. If the passages "
                  "don't answer it, say so. Return JSON: {\"answer\": str, \"used\": [passage numbers]}.")
        try:
            out = json.loads(re.search(r"\{.*\}", llm.complete(system, f"Question: {question}\n\nPassages:\n{listing}"), re.S).group(0))
            used = [items[i] for i in out.get("used", []) if isinstance(i, int) and 0 <= i < len(items)]
            if used:
                return out["answer"], used, "claude"
        except Exception:
            pass
    top = items[:3]
    text = " ".join(norm(it["text"]).rstrip(".") + "." for it in top)
    text = re.sub(r"^(Decision|Why|Owner|Must-have|Plan):\s*", "", text)
    for rx, subject in ROLE_RULES:
        if rx.search(question):
            vp = "Vice President" in p["role"] or "VP" in p["role"] or p["role"] == "CEO"
            text = ("Yes, as a Vice President you can approve it. " if vp else
                    "Not on your own: purchases from $5,000 to $25,000 need a department director's approval. ") + text
    return text, top, "extractive"


def ask(person, question):
    where, args = access.item_filter_sql(person)
    allowed = search(question, where, args)
    if re.search(r"decid|decision|agreed|resolved", question, re.I):   # decisions first when asked about them
        dec = search(question, f"{where} AND i.type = 'decision' AND i.source_id LIKE '%/decisions/%'", args, k=1)
        if dec:  # the whole decision record, in reading order
            dec = db.q(f"SELECT i.*, 0 AS score FROM items i WHERE i.source_id = ? AND {where} ORDER BY i.span_start", [dec[0]["source_id"]] + list(args))
        allowed = dec + [a for a in allowed if a["id"] not in {d["id"] for d in dec}]
    best_any = search(question, k=3)        # system-level probe; never returned to the asker
    blocked = None
    # A question that names a unit the asker can't read is blocked for that unit, whatever else matches.
    for sc, meta in db.ORG["scopes"].items():
        named = meta["kind"] in ("team", "dept") and re.search(rf"\b{re.escape(meta['name'])}('s)?\b", question, re.I)
        if named and access.can_read_scope(person, sc):
            first = search(question, f"{where} AND (i.scope = ? OR i.scope LIKE ? || '/%')", list(args) + [sc, sc], k=4)
            allowed = first + [a for a in allowed if a["id"] not in {f["id"] for f in first}]
            continue
        if named:
            best_any = [r for r in search(question, "(i.scope = ? OR i.scope LIKE ? || '/%')", [sc, sc])] or best_any
            if best_any and access.below(best_any[0]["scope"], sc):
                allowed = []
            break
    if best_any:
        top = best_any[0]
        if not access.can_read_item(person, top) and top["status"] != "draft":
            gap = (allowed[0]["score"] - top["score"]) if allowed else 99
            if gap > 1.0:
                sc = top["scope"]
                pending = db.q("SELECT 1 FROM requests WHERE who=? AND scope=? AND status='waiting'", (person, sc))
                blocked = {"scope": sc, "scope_name": db.ORG["scopes"][sc]["name"],
                           "owner": db.ORG["scopes"][sc]["owner"],
                           "approvers": access.approvers_for(sc, person), "pending": bool(pending),
                           "restricted": top["sensitivity"] == "restricted"}
    db.audit(person, "ask", {"q": question, "allowed": [r["id"] for r in allowed],
                             "blocked_scope": blocked and blocked["scope"]}, access.TODAY)
    if blocked:
        return {"status": "blocked", "blocked": blocked,
                "graph": {"nodes": [["q", question[:57], "q"], ["l", "Locked: " + blocked["scope_name"], "k"],
                                    ["o", db.ORG["people"][blocked["owner"]]["name"], "p"]],
                          "edges": [["q", "l", "blocked"], ["l", "o", "owned by"]]},
                "access_note": f"Blocked before search: {blocked['scope_name']} is outside "
                               f"{db.ORG['people'][person]['name']}'s area"
                               f"{' and is restricted' if blocked['restricted'] else ''}. Nothing from it reached the model."}
    if not allowed:
        return {"status": "none", "answer": "I couldn't find anything about that in the areas you can access.",
                "cites": [], "graph": {"nodes": [["q", question[:57], "q"]], "edges": []}, "access_note": ""}
    text, used, mode = answer_text(question, person, allowed)
    notes = {access.access_note(person, it) for it in used}
    pieces = []
    if "own" in notes:
        pieces.append(f"Inside {db.ORG['people'][person]['name']}'s own area")
    if "published" in notes:
        pieces.append("published down from a higher level")
    for n in notes:
        if n.startswith("grant:"):
            g = db.q("SELECT * FROM grants WHERE id=?", (int(n[6:]),))[0]
            pieces.append(f"read under a grant from {db.ORG['people'][g['granted_by']]['name']} "
                          f"for “{g['label']}”, expiring {g['expires']}; this use was logged")
            db.audit(person, "grant_use", {"grant": g["id"]}, access.TODAY)
    cites = [cite(it) for it in used]
    return {"status": "ok", "answer": text, "mode": mode, "cites": cites, "graph": graph(question, used),
            "access_note": (lambda t: t[:1].upper() + t[1:])("; ".join(pieces)) + ". Every quote was matched to its source file."
            if all(c["verified"] for c in cites) else "; ".join(pieces)}
