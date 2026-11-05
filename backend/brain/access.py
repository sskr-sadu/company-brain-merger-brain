"""Top-down access with grants.

A person reads: their own area and everything below it; items a higher level publishes down to them;
contracts their unit is party to; and any scope covered by a live grant. Restricted items need the CEO or the
head of the owning department, and a grant never lifts that. Locked categories never appear in search.
Members' drafts are visible only to the member.
"""
from . import db

ORG = db.ORG
SCOPES, PEOPLE = ORG["scopes"], ORG["people"]
TODAY = ORG["today"]


def parent(s):
    return s.rsplit("/", 1)[0] if "/" in s else None


def below(s, root):
    return s == root or s.startswith(root + "/")


def lca(a, b):
    x = a
    while x and not below(b, x):
        x = parent(x)
    return x or "org"


def dept_of(scope):
    return "/".join(scope.split("/")[:2]) if scope != "org" else "org"


def live_grants(person):
    return db.q("SELECT * FROM grants WHERE who=? AND revoked=0 AND expires>?", (person, TODAY))


def can_read_scope(person, scope):
    p = PEOPLE[person]
    if below(scope, p["access"]) or (p.get("own") and below(scope, p["own"])):
        return True
    return any(below(scope, g["scope"]) for g in live_grants(person))


def item_filter_sql(person):
    """SQL WHERE clause (and args) selecting the items `person` may read. Runs before any text reaches a model."""
    p = PEOPLE[person]
    acc = p["access"]
    clauses = ["(i.scope = ? OR i.scope LIKE ? || '/%')",                  # own area and below
               "(i.publish_down = 1 AND (? = i.scope OR ? LIKE i.scope || '/%'))"]  # published down from above
    args = [acc, acc, acc, acc]
    for g in live_grants(person):
        clauses.append("(i.scope = ? OR i.scope LIKE ? || '/%')")
        args += [g["scope"], g["scope"]]
    own = p.get("own")
    vis = " OR ".join(clauses)
    draft_rule = "(i.status != 'draft' OR i.scope = ?)"
    args.append(own or "-")
    # Members never see other members' private scopes, even inside their own team.
    member_rule = "NOT (i.scope LIKE '%/%/%/%' AND i.scope != ?)"
    args.append(own or "-")
    sens = ("(i.sensitivity = 'internal' OR (i.sensitivity = 'restricted' AND (? = 'org' OR ? = substr(i.scope, 1, length(?)))))")
    # Only the CEO or the head of the owning department reads restricted items.
    d = acc if SCOPES[acc]["kind"] == "dept" else "__none__"
    args += [acc, d, d]
    if PEOPLE[person]["access"] != "org" and person not in ORG["locked_access"]:
        sens = f"({sens} AND i.sensitivity != 'locked')"
    src = "i.source_id NOT IN (SELECT id FROM sources WHERE quarantined = 1)"
    return f"(({vis}) AND {draft_rule} AND {member_rule} AND {sens} AND {src})", args


def can_read_item(person, item):
    where, args = item_filter_sql(person)
    return bool(db.q(f"SELECT 1 FROM items i WHERE i.id = ? AND {where}", [item["id"]] + args))


def approvers_for(scope, requester):
    """Inside a department: the person supervising both teams, or the owner (lead or point of contact)
    of the team that holds the data. Across departments: the CEO or the head of the owning department."""
    a = PEOPLE[requester]["access"]
    sup = SCOPES[lca(a, scope)]["owner"]
    out = [sup]
    same_dept = dept_of(a) == dept_of(scope)
    if same_dept:
        tgt = SCOPES.get(scope, {})
        out.append(tgt.get("poc") or tgt.get("owner"))
    else:
        out.append(SCOPES[dept_of(scope)]["owner"])
    out.append("dana")
    seen, res = set(), []
    for o in out:
        if o and o != requester and o not in seen:
            seen.add(o)
            res.append(o)
    return res


def access_note(person, item):
    p = PEOPLE[person]
    if below(item["scope"], p["access"]) or (p.get("own") and below(item["scope"], p["own"])):
        return "own"
    if item.get("publish_down") and below(p["access"], item["scope"]):
        return "published"
    for g in live_grants(person):
        if below(item["scope"], g["scope"]):
            return f"grant:{g['id']}"
    return "contract"
