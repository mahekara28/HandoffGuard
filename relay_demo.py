"""Run in an environment with Context Relay installed, alongside the local desk."""
from context_relay import ContextGuard

from agent_api import BASE, intake_packet, wait_for_release

SOURCE = "Reuse the same payment key for every retry of one logical payment."


def intake(tool, args):
    # Source and task identity belong to the host. Only the proposed handoff comes from the tool.
    packet = intake_packet("Relay payment demo", SOURCE, args["instruction"])
    return {"review_id": packet["id"]}


def main():
    with ContextGuard(name="HandoffGuard intake") as guard:
        guard.allow_tool("submit_handoff", optional_args=("instruction",))
        result = guard.turn().execute_with_recovery("submit_handoff", {"instruction": SOURCE}, intake)
        if result["status"] != "executed":
            raise SystemExit("Relay held the tool call: " + result["status"])
        key = result["result"]["review_id"]
    print("Packet submitted. Open the review desk:", BASE, flush=True)
    print("Released to receiving agent:", wait_for_release(key))


if __name__ == "__main__":
    main()
