"""Two ADK agents separated by the HandoffGuard release endpoint."""
import argparse
import asyncio
import json
import os
import uuid
from urllib.request import Request, urlopen

BASE = os.getenv("HANDOFF_URL", "http://localhost:8502").rstrip("/")


def desk(path, data=None):
    headers = {"Content-Type": "application/json"}
    if os.getenv("HANDOFF_ID_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["HANDOFF_ID_TOKEN"]
    req = Request(BASE+path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    with urlopen(req, timeout=65) as response:
        return json.load(response)


async def agent_reply(name, instruction, prompt):
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types
    agent = Agent(name=name, model=os.environ["GEMINI_MODEL"], instruction=instruction)
    runner = InMemoryRunner(agent=agent, app_name="handoffguard")
    session = await runner.session_service.create_session(app_name="handoffguard", user_id="demo")
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    async for event in runner.run_async(user_id="demo", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content:
            reply = "".join(p.text for p in event.content.parts if p.text and not p.thought)
            if reply.strip():
                return reply
    raise RuntimeError(f"{name} returned no handoff text.")


async def run(change):
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    source = "Keep the deprecated API alias. Existing clients still call it."
    note = await agent_reply("researcher", "Write a one-sentence handoff preserving the user's API compatibility requirement.", source)
    # Deliberately simulate a modified message in the contradiction demo.
    handoff = "Remove the deprecated API alias." if change else note
    r = await asyncio.to_thread(desk, "/api/reviews", {"reference":"ADK alias review "+uuid.uuid4().hex[:8],
                                 "source":"Original task: "+source+"\nResearch agent: "+note, "handoff":handoff})
    print("Open the desk to inspect", r["reference"], flush=True)
    path = "/api/reviews/" + r["id"]
    for _ in range(120):
        if r["state"] == "approved":
            released = await asyncio.to_thread(desk, path+"/release")
            print(await agent_reply("implementer", "Write a brief implementation plan for the approved instruction.", released["handoff"]))
            return
        if r["state"] not in ("pending","checking"):
            print("Implementation held:", r["state"])
            return
        await asyncio.sleep(2)
        r = await asyncio.to_thread(desk, path)
    print("Review still pending. The implementation agent did not start.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--change", action="store_true", help="Simulate an instruction changed in transit")
    asyncio.run(run(parser.parse_args().change))


