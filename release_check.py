"""Run the release lifecycle against a disposable database."""
from pathlib import Path
from tempfile import TemporaryDirectory

from review import Problem, decide, released, submit
from storage import Store


def run_check():
    steps = []
    with TemporaryDirectory() as folder:
        store = Store(Path(folder) / "demo.sqlite")
        source = "Keep the deprecated API alias."
        task = {"reference": "API compatibility", "source": source}

        def record(label, condition):
            steps.append({"label": label, "passed": bool(condition)})

        def held(key):
            try:
                released(store.get(key))
            except Problem as exc:
                return exc.code == 409
            return False

        first = submit(dict(task, handoff=source), test_store=store)
        decide(first["id"], "approved", store=store)
        record("Approved revision 1 can be released", released(store.get(first["id"]))["revision"] == 1)
        changed = submit(dict(task, revises=first["id"], handoff="Remove the deprecated API alias."), test_store=store)
        record("The changed instruction is flagged", changed["finding"]["status"] == "conflict")
        record("The old approval stops working", held(first["id"]))
        decide(changed["id"], "rejected", store=store)
        record("The rejected instruction stays held", held(changed["id"]))
        fixed = submit(dict(task, revises=changed["id"], handoff=source), test_store=store)
        decide(fixed["id"], "approved", store=store)
        delivered = released(store.get(fixed["id"]))
        record("Only corrected revision 3 is released",
               delivered["revision"] == 3 and delivered["handoff"] == source and held(changed["id"]) and held(first["id"]))
    return {"passed": all(step["passed"] for step in steps), "steps": steps}
