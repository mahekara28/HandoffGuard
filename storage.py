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


class StaleRevision(Exception):
    pass


class Store:
    def __init__(self, path=None):
        project = None if path else os.getenv("GOOGLE_CLOUD_PROJECT")
        self.client = cloud_client(project) if project else None
        self.cloud = self.client.collection("handoff_packets") if self.client is not None else None
        self.path = path or os.getenv("HANDOFF_DB") or str(Path(__file__).with_name("reviews.sqlite"))
        if self.cloud is None:
            with closing(self.connect()) as db, db:
                db.execute("CREATE TABLE IF NOT EXISTS packets (id TEXT PRIMARY KEY, updated REAL, data TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT)")
                db.execute("CREATE INDEX IF NOT EXISTS packets_updated ON packets(updated DESC)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def atomic(self, operation):
        """All reads precede writes so one operation works in either backend."""
        if self.cloud is not None:
            from google.cloud import firestore
            collections = {"packets": self.cloud, "tasks": self.client.collection("handoff_tasks")}

            @firestore.transactional
            def apply(tx):
                def read(table, key):
                    return collections[table].document(key).get(transaction=tx).to_dict()

                def write(table, key, value):
                    tx.set(collections[table].document(key), value)

                return operation(read, write)
            return apply(self.client.transaction())

        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")

            def read(table, key):
                row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
                return json.loads(row[0]) if row else None

            def write(table, key, value):
                if table == "tasks":
                    db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (key, json.dumps(value)))
                else:
                    db.execute("INSERT OR REPLACE INTO packets VALUES (?,?,?)",
                               (key, value["updated"], json.dumps(value)))

            return operation(read, write)

    def change(self, key, transform):
        def apply(read, write):
            old = read("packets", key)
            new = transform(old)
            if new is not None:
                write("packets", key, new)
            return new or old
        return self.atomic(apply)

    def claim(self, task_id, key, parent, transform):
        def apply(read, write):
            old = read("packets", key)
            new = transform(old)
            if new is None:
                return old
            head = read("tasks", task_id)
            current = head["id"] if head else None
            if current != key and parent and parent != current:
                raise StaleRevision("A newer revision exists. Open the latest review to edit it.")
            revision = head["revision"] if head else 0
            if current != key:
                revision += 1
                if current:
                    prior = read("packets", current)
                    prior.update(state="superseded", updated=new["updated"])
                    prior["events"].append({"at": new["updated"], "label": "Replaced by revision " + str(revision)})
                    write("packets", current, prior)
                write("tasks", task_id, {"id": key, "revision": revision})
            new.update(task_id=task_id, revision=revision)
            write("packets", key, new)
            return new
        return self.atomic(apply)

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
