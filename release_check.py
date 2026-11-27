"""Run the release lifecycle against a disposable database."""
import os
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

        first = submit(dict(task, handoff=source), test_store=store, offline=True)
        decide(first["id"], "approved", store=store)
        record("Approved revision 1 can be released", released(store.get(first["id"]))["revision"] == 1)
        changed = submit(dict(task, revises=first["id"], handoff="Remove the deprecated API alias."), test_store=store, offline=True)
        record("The changed instruction is flagged", changed["finding"]["status"] == "conflict")
        record("The old approval stops working", held(first["id"]))
        decide(changed["id"], "rejected", store=store)
        record("The rejected instruction stays held", held(changed["id"]))
        fixed = submit(dict(task, revises=changed["id"], handoff=source), test_store=store, offline=True)
        decide(fixed["id"], "approved", store=store)
        delivered = released(store.get(fixed["id"]))
        record("Only corrected revision 3 is released",
               delivered["revision"] == 3 and delivered["handoff"] == source and held(changed["id"]) and held(first["id"]))
    return {"passed": all(step["passed"] for step in steps), "steps": steps}


def run_gemini_demo():
    if not os.getenv("GEMINI_API_KEY") or not os.getenv("GEMINI_MODEL"):
        raise Problem(503, "Start the desk with python app.py --gemini and enter your API key and model ID.")
    task = {"reference": "Gemini demo", "source": "Keep the deprecated getUser() alias. Existing mobile clients use it."}
    cases = [
        ("Remove the deprecated getUser() alias.", "conflict", "rejected"),
        ("Keep getUser() available as an alias for existing mobile clients.", "aligned", "approved"),
    ]
    steps = []
    parent = None
    with TemporaryDirectory() as folder:
        store = Store(Path(folder) / "live-demo.sqlite")
        for instruction, expected, decision in cases:
            packet = submit(dict(task, handoff=instruction, revises=parent), test_store=store)
            finding = packet["finding"]
            step = {"label": "Changed handoff" if parent is None else "Corrected handoff",
                    "status": finding["status"], "reason": finding["reason"], "engine": packet["engine"],
                    "source_quote": finding.get("source_quote"), "handoff_quote": finding.get("handoff_quote"),
                    "passed": False}
            steps.append(step)
            if packet["state"] != "pending" or finding["status"] != expected:
                break
            decided = decide(packet["id"], decision, "Demo runner", store=store)
            if decision == "approved":
                step["passed"] = released(decided)["handoff"] == instruction
                step["label"] += " · released"
            else:
                try:
                    released(decided)
                except Problem as exc:
                    step["passed"] = exc.code == 409
                step["label"] += " · rejected"
            if not step["passed"]:
                break
            parent = packet["id"]
    return {"passed": len(steps) == len(cases) and all(s["passed"] for s in steps), "steps": steps}
