# team_min_chutes.py
# Steps 2–5 with Chutes.ai, no custom TerminationCondition import needed.

import os, time, asyncio
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console

from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from autogen_ext.tools.code_execution import PythonCodeExecutionTool

# ---------- STEP 2: Chutes creds & endpoint ----------
CHUTES_API_KEY = "cpk_6409376b53ff4bcda0bed0b6e71b2abe.105ceb10f63a5052bf24ac406ffcf330.9IVsa2JTvSIgVL1nUCSOCfOpBlKvcust"
CHUTES_BASE_URL = os.environ.get("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
# MODEL_NAME = "Qwen/Qwen2.5-Coder-32B-Instruct"
MODEL_NAME = "moonshotai/Kimi-K2-Instruct-75k"
# MODEL_NAME = "openai/gpt-oss-120b"

# Required for non-OpenAI model names:
MODEL_INFO = {
    "vision": False,
    "function_calling": True,
    "json_output": False,
    "structured_output": False,
    "family": "unknown",
}

async def try_print_stream_usage(model_client):
    try:
        from autogen_core.models import UserMessage
        stream = model_client.create_stream(
            messages=[UserMessage(content="Say 'hi' in one word.", source="user")],
            extra_create_args={"stream_options": {"include_usage": True}},
        )
        usage = None
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
        print("Token usage:", usage if usage else "(provider did not return usage in stream)")
    except Exception as e:
        print(f"(Usage check skipped): {e}")

async def main():
    os.makedirs("sandbox", exist_ok=True)

    # ---------- STEP 3: Minimal multi-agent coding team ----------
    model = OpenAIChatCompletionClient(
        model=MODEL_NAME,
        api_key=CHUTES_API_KEY,
        base_url=CHUTES_BASE_URL,   # must end with /v1
        temperature=0.2,
        include_name_in_message=True,
        model_info=MODEL_INFO,
    )

    exec_tool = PythonCodeExecutionTool(LocalCommandLineCodeExecutor(work_dir="sandbox"))

    planner = AssistantAgent("Planner", model_client=model)
    coder   = AssistantAgent("Coder",   model_client=model, tools=[exec_tool])
    tester  = AssistantAgent("Tester",  model_client=model, tools=[exec_tool])

    # Terminate when pytest reports success (e.g., "2 passed in 0.03s") OR after 40 turns.
    team = RoundRobinGroupChat(
        [planner, coder, tester],
        termination_condition=TextMentionTermination(" passed in ") | MaxMessageTermination(40),
    )

    # IMPORTANT: Do NOT include any success token in this prompt (prevents false positives).
    task = """You are a team solving a tiny coding task.

Implement function sum_of_squares(nums: list[int]) -> int in a file sandbox/solution.py.
Also create sandbox/test_solution.py with pytest tests (cover normal and edge cases).
Use the Python execution tool to write files (Python file I/O), then run tests with:
  python -m pytest -q
Tester: after each run, paste ONLY the last non-empty line of pytest output.
Iterate until tests pass. Keep outputs concise.
"""

    t0 = time.time()
    result = await Console(team.run_stream(task=task))
    dt = time.time() - t0

    print("\n--- SUMMARY ---")
    print(f"Elapsed seconds: {dt:.2f}")
    try:
        print(f"Messages exchanged: {len(result.messages)}")
    except Exception:
        pass

    # ---------- STEP 5: optional usage sanity ----------
    await try_print_stream_usage(model)

if __name__ == "__main__":
    asyncio.run(main())
