"""Two ADK agents separated by the HandoffGuard release endpoint."""
import argparse
import asyncio
import os
import uuid
from agent_api import intake_packet, wait_for_release


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
    reference = "ADK alias review " + uuid.uuid4().hex[:8]
    transcript = "Original task: " + source + "\nResearch agent: " + note
    r = await asyncio.to_thread(intake_packet, reference, transcript, handoff)
    print("Open the desk to inspect", reference, flush=True)
    instruction = await asyncio.to_thread(wait_for_release, r["id"])
    print(await agent_reply("implementer", "Write a brief implementation plan for the approved instruction.", instruction))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--change", action="store_true", help="Simulate an instruction changed in transit")
    asyncio.run(run(parser.parse_args().change))
