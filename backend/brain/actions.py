"""Real side effects, run only after a person approves: a GitHub issue, and a decision written back into the
brain as a new source file so later answers cite it."""
import json
import os
import re
import urllib.request

from . import access, db, ingest


def github_issue(title, body):
    repo, token = os.environ.get("GITHUB_REPO"), os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return {"created": False, "reason": "Set GITHUB_REPO=owner/repo and GITHUB_TOKEN to create real issues."}
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues",
                                 data=json.dumps({"title": title, "body": body}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        return {"created": True, "url": data.get("html_url"), "number": data.get("number")}
    except Exception as e:  # never break the decision because GitHub is down
        return {"created": False, "reason": f"GitHub call failed: {e}"}


def write_decision(conflict, option, person, plans=None):
    """Write the decision into the scope's folder and ingest it, closing the loop: the brain now knows."""
    scope_dir = db.ORG["scopes"][conflict["scope"]]["dir"]
    folder = db.DATA / db.ORG["company"] / scope_dir / "decisions"
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", conflict["title"].lower()).strip("-")[:50]
    path = folder / f"{access.TODAY}-{slug}.md"
    who = db.ORG["people"][person]["name"]
    ev = json.loads(conflict["evidence"])
    sens = "internal"
    path.write_text(
        "---\n"
        f"company: {db.ORG['company']}\nscope: {scope_dir}\nsource_type: decision_log\nauthority: 4\n"
        f"date: {access.TODAY}\nauthor: {who}\nsensitivity: {sens}\n"
        + ("status: draft\n" if conflict["kind"] == "drift" else "publish: down\n") +
        "---\n\n"
        f"# Decision: {conflict['title']}\n\n"
        f"- Decision: {option}.\n"
        f"- About: {conflict['title']}.\n"
        f"- Decided by: {who}, on {access.TODAY}.\n"
        f"- Raised by the brain's {conflict['trigger']} trigger, based on: {ev[0][2]} and {ev[1][2]}.\n"
        + "".join(f"- Plan step: {st['what']} (owner {db.ORG['people'][st['owner']]['name']}, due {st['due']}).\n"
                  for p in (plans or []) if p["option"] == option for st in p["steps"]))
    report = ingest.ingest_file(path)
    return path.relative_to(db.DATA).as_posix(), report
