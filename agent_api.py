"""Transport shared by the Context Relay and ADK demos."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.getenv("HANDOFF_URL", "http://127.0.0.1:8502").rstrip("/")


def request(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(data).encode() if data is not None else None
    with urlopen(Request(BASE + path, data=body, headers=headers), timeout=65) as response:
        return json.load(response)


def intake_packet(reference, source, handoff):
    data = {"reference": reference, "source": source, "handoff": handoff}
    if os.getenv("HANDOFF_RECEIVER_UID"):
        data["receiver_uid"] = os.environ["HANDOFF_RECEIVER_UID"]
    return request("/api/reviews", data, os.getenv("HANDOFF_ID_TOKEN"))


def wait_for_release(key):
    scoped = bool(os.getenv("HANDOFF_RECEIVER_UID"))
    token = os.getenv("HANDOFF_RECEIVER_TOKEN" if scoped else "HANDOFF_ID_TOKEN")
    prefix = "/api/receiver/" if scoped else "/api/reviews/"
    for _ in range(120):
        try:
            return request(prefix + key + "/release", token=token)["handoff"]
        except HTTPError as exc:
            if exc.code != 409:
                raise
            reason = json.load(exc).get("error", "")
            if reason not in ("Release held: pending", "Release held: checking"):
                raise SystemExit(reason)
        time.sleep(2)
    raise SystemExit("Still awaiting approval.")
