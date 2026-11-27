"""Run in an environment with Context Relay installed, alongside the local desk."""
import json
import os
import time
from urllib.request import Request, urlopen

from context_relay import ContextGuard

SOURCE = "Reuse the same payment key for every retry of one logical payment."
BASE = os.environ.get("HANDOFF_URL", "http://127.0.0.1:8502").rstrip("/")


def request(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"}
    if os.getenv("HANDOFF_ID_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["HANDOFF_ID_TOKEN"]
    with urlopen(Request(BASE + path, data=body, headers=headers), timeout=60) as response:
        return json.load(response)


def intake(tool, args):
    # Source and task identity belong to the host. Only the proposed handoff comes from the tool.
    packet = request("/api/reviews", {"reference": "Relay payment demo", "source": SOURCE, "handoff": args["instruction"]})
    return {"review_id": packet["id"]}


def main():
    with ContextGuard(name="HandoffGuard intake") as guard:
        guard.allow_tool("submit_handoff", optional_args=("instruction",))
        result = guard.turn().execute_with_recovery("submit_handoff", {"instruction": SOURCE}, intake)
        if result["status"] != "executed":
            raise SystemExit("Relay held the tool call: " + result["status"])
        key = result["result"]["review_id"]
    print("Packet submitted. Open the review desk:", BASE, flush=True)
    path = "/api/reviews/" + key
    for _ in range(120):
        state = request(path)["state"]
        if state == "approved":
            approved = request(path + "/release")
            print("Released to receiving agent:", approved["handoff"])
            return
        if state not in ("checking", "pending"):
            raise SystemExit("Receiving agent held: " + state)
        time.sleep(2)
    raise SystemExit("Still awaiting review. Run again to resume the same packet.")


if __name__ == "__main__":
    main()



