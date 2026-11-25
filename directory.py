"""Contact-only directory. Mount behind middleware that sets WSGI REMOTE_USER."""
import json
import sqlite3
import time
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS contact (
    owner TEXT NOT NULL, member TEXT NOT NULL, PRIMARY KEY(owner, member)
);
CREATE TABLE IF NOT EXISTS device (
    id TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL, name TEXT NOT NULL,
    expires_at INTEGER NOT NULL DEFAULT 0
);
"""
VISIBLE = """
SELECT d.id, d.name FROM device AS d JOIN contact AS c ON c.owner = d.owner
WHERE c.member = ? AND d.expires_at > ?
"""


class Directory:
    def __init__(self, database, clock=time.time):
        self.database = database
        self.clock = clock
        with closing(sqlite3.connect(database)) as db:
            db.executescript(SCHEMA)

    def __call__(self, environ, start_response):
        actor = environ.get("REMOTE_USER")
        if not actor:
            status, data = "401 Unauthorized", {}
        else:
            with closing(sqlite3.connect(self.database)) as db, db:
                status, data = self.route(db, actor, environ)
        payload = json.dumps(data, ensure_ascii=False).encode()
        start_response(status, [("Content-Type", "application/json"),
                                ("Cache-Control", "no-store"),
                                ("Content-Length", str(len(payload)))])
        return [payload]

    def route(self, db, actor, env):
        method, path = env["REQUEST_METHOD"], env["PATH_INFO"]
        now = int(self.clock())
        if method == "GET" and path == "/devices":
            rows = db.execute(VISIBLE + " ORDER BY d.id", (actor, now))
            return "200 OK", [{"id": key, "name": name} for key, name in rows]

        # Recheck the same policy even when the caller already knows the ID.
        if method == "POST" and path.startswith("/requests/"):
            key = path.removeprefix("/requests/")
            allowed = db.execute(VISIBLE + " AND d.id = ?", (actor, now, key)).fetchone()
            if allowed:
                return "200 OK", {"eligible": True}
        return "404 Not Found", {}
