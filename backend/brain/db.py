"""SQLite store: the brain's system of record. Rebuildable at any time from the files in data/."""
import hashlib
import json
import pathlib
import sqlite3
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]          # merger-brain/
DATA = ROOT / "data"
DB_PATH = ROOT / "backend" / "brain.db"
ORG = json.loads((ROOT / "backend" / "org.json").read_text())

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, path TEXT, scope TEXT, source_type TEXT, authority INTEGER, date TEXT,
  author TEXT, sensitivity TEXT, status TEXT, sha256 TEXT, quarantined INTEGER DEFAULT 0, quarantine_reason TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, source_id TEXT, scope TEXT, type TEXT, strength TEXT, text TEXT,
  span_start INTEGER, span_end INTEGER, date TEXT, sensitivity TEXT, status TEXT,
  publish_down INTEGER DEFAULT 0, authority INTEGER, subjects TEXT, entities TEXT, owner TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(id UNINDEXED, text, tokenize='porter');
CREATE TABLE IF NOT EXISTS contracts (
  id TEXT PRIMARY KEY, scope TEXT, title TEXT, provider TEXT, consumer TEXT, provider_owner TEXT, consumer_owner TEXT,
  must_have TEXT, must_have_date TEXT, subject TEXT, source_id TEXT);
CREATE TABLE IF NOT EXISTS conflicts (
  id TEXT PRIMARY KEY, kind TEXT, trigger TEXT, scope TEXT, title TEXT, evidence TEXT, extra TEXT,
  route TEXT, options TEXT, visible_to TEXT, notify TEXT, status TEXT DEFAULT 'open', decision TEXT,
  decided_by TEXT, decided_at TEXT, action_result TEXT, created_at TEXT,
  origin TEXT, affected TEXT, actor TEXT, checks TEXT);
CREATE TABLE IF NOT EXISTS prs (number INTEGER PRIMARY KEY, author TEXT, title TEXT, base TEXT, checks TEXT,
  conflict_id TEXT, affected TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, scope TEXT, label TEXT, why TEXT, status TEXT DEFAULT 'waiting',
  approvers TEXT, decided_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS grants (
  id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, scope TEXT, label TEXT, granted_by TEXT, expires TEXT, request_id INTEGER, revoked INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, who TEXT, title TEXT, hours REAL, day TEXT, priority INTEGER,
  critical TEXT, off_plan TEXT, feeds TEXT, needs TEXT);
CREATE TABLE IF NOT EXISTS completed (who TEXT, date TEXT, time TEXT, title TEXT, ref TEXT);
CREATE TABLE IF NOT EXISTS milestones (scope TEXT, date TEXT, label TEXT, progress INTEGER, state TEXT, risk INTEGER);
CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, to_person TEXT, text TEXT, ref TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS trigger_state (name TEXT PRIMARY KEY, rows TEXT);
CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, detail TEXT, prev_hash TEXT, hash TEXT);
"""

_lock = threading.RLock()
_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def reset():
    """Drop everything and recreate the schema (used by a full re-ingest)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        if DB_PATH.exists():
            DB_PATH.unlink()
        conn()


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def x(sql, args=()):
    with _lock:
        cur = conn().execute(sql, args)
        conn().commit()
        return cur


def audit(actor, action, detail, ts):
    """Append-only, hash-chained audit log: each row stores the hash of the row before it."""
    with _lock:
        last = conn().execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "genesis"
        payload = json.dumps([ts, actor, action, detail], sort_keys=True)
        h = hashlib.sha256((prev + payload).encode()).hexdigest()
        conn().execute("INSERT INTO audit (ts, actor, action, detail, prev_hash, hash) VALUES (?,?,?,?,?,?)",
                       (ts, actor, action, json.dumps(detail), prev, h))
        conn().commit()


def verify_audit():
    prev = "genesis"
    for r in q("SELECT * FROM audit ORDER BY seq"):
        payload = json.dumps([r["ts"], r["actor"], r["action"], json.loads(r["detail"])], sort_keys=True)
        if r["prev_hash"] != prev or hashlib.sha256((prev + payload).encode()).hexdigest() != r["hash"]:
            return False, r["seq"]
        prev = r["hash"]
    return True, None
