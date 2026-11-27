"""Atomic per-packet updates shared by the dashboard and agent API."""
import json
import os
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path


@lru_cache
def cloud_client(project):
    from google.cloud import firestore
    return firestore.Client(project=project)


class Store:
    def __init__(self):
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.client = cloud_client(project) if project else None
        self.cloud = self.client.collection("handoff_packets") if self.client is not None else None
        self.path = os.getenv("HANDOFF_DB") or str(Path(__file__).with_name("reviews.sqlite"))
        if self.cloud is None:
            with closing(self.connect()) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS packets (id TEXT PRIMARY KEY, updated REAL, data TEXT)")
                db.execute("CREATE INDEX IF NOT EXISTS packets_updated ON packets(updated DESC)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def change(self, key, transform):
        """A transform returning None leaves the current packet untouched."""
        if self.cloud is not None:
            from google.cloud import firestore
            ref = self.cloud.document(key)

            @firestore.transactional
            def apply(tx):
                old = ref.get(transaction=tx).to_dict()
                new = transform(old)
                if new is not None:
                    tx.set(ref, new)
                return new or old

            return apply(self.client.transaction())
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM packets WHERE id=?", (key,)).fetchone()
            old = json.loads(row[0]) if row else None
            new = transform(old)
            if new is not None:
                db.execute("INSERT OR REPLACE INTO packets VALUES (?,?,?)",
                           (key, new["updated"], json.dumps(new)))
            return new or old

    def get(self, key):
        if self.cloud is not None:
            return self.cloud.document(key).get().to_dict()
        with closing(self.connect()) as db:
            row = db.execute("SELECT data FROM packets WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent(self):
        if self.cloud is not None:
            return [doc.to_dict() for doc in self.cloud.order_by("updated", direction="DESCENDING").limit(100).stream()]
        with closing(self.connect()) as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM packets ORDER BY updated DESC LIMIT 100")]


