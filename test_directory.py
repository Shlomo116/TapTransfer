import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from wsgiref.util import setup_testing_defaults
import json

from directory import Directory


class ContactAccess(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "directory.sqlite"
        self.app = Directory(self.path, clock=lambda: 100)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executemany("INSERT INTO device VALUES (?, ?, ?, ?)", [
                ("phone", "owner", "Phone", 101), ("mac", "owner", "Mac", 110),
                ("expired", "owner", "Expired", 100), ("other", "friend", "Other", 110)])
            db.execute("INSERT INTO contact VALUES ('owner', 'friend')")

    def call(self, actor, path="/devices", **extra):
        env = {}
        setup_testing_defaults(env)
        env.update(REMOTE_USER=actor, PATH_INFO=path,
                   REQUEST_METHOD="GET" if path == "/devices" else "POST", **extra)
        status = []
        payload = self.app(env, lambda code, headers: status.append(code))
        return status[0][:3], json.loads(b"".join(payload))

    def test_direction_and_multiple_devices(self):
        code, devices = self.call("friend")
        self.assertEqual(code, "200")
        self.assertEqual([d["id"] for d in devices], ["mac", "phone"])
        self.assertEqual(self.call("owner"), ("200", []))
        self.assertEqual(self.call("stranger"), ("200", []))

    def test_direct_request_rechecks_after_removal(self):
        self.assertEqual(self.call("friend", "/requests/phone")[0], "200")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM contact")
        self.assertEqual(self.call("friend"), ("200", []))
        self.assertEqual(self.call("friend", "/requests/phone"), ("404", {}))

    def test_hidden_expired_and_unknown_look_the_same(self):
        for actor, device in [("stranger", "phone"), ("friend", "expired"),
                              ("friend", "missing")]:
            with self.subTest(actor=actor, device=device):
                self.assertEqual(self.call(actor, "/requests/" + device), ("404", {}))

    def test_client_header_is_not_identity(self):
        for path in ("/devices", "/requests/phone"):
            self.assertEqual(self.call(None, path, HTTP_REMOTE_USER="friend")[0], "401")


if __name__ == "__main__":
    unittest.main()
