# team_min_chutes_final.py
import os, shlex, time, asyncio, subprocess
from typing import List
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.code_executors.local import LocalCommandLineCodeExecutor
from autogen_ext.tools.code_execution import PythonCodeExecutionTool

CHUTES_API_KEY  = os.environ.get("CHUTES_API_KEY",  "cpk_6409376b53ff4bcda0bed0b6e71b2abe.105ceb10f63a5052bf24ac406ffcf330.9IVsa2JTvSIgVL1nUCSOCfOpBlKvcust")
CHUTES_BASE_URL = os.environ.get("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
PREFERRED_MODELS: List[str] = [
    "moonshotai/Kimi-K2-Instruct-75k",
    "openai/gpt-oss-120b",
    "deepseek-ai/DeepSeek-V3-0324",
    "openai/gpt-oss-20b",
]
BASE_MODEL_INFO = {
    "vision": False, "function_calling": True, "json_output": False,
    "structured_output": False, "family": "unknown",
}
DOCKER_IMAGE = os.environ.get("PY_SANDBOX_IMAGE", "python:3.10")
MAX_TURNS = 12

def make_client(model_name: str) -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=model_name, api_key=CHUTES_API_KEY, base_url=CHUTES_BASE_URL,
        temperature=0.2, include_name_in_message=True, model_info=BASE_MODEL_INFO
    )

async def preflight(client: OpenAIChatCompletionClient) -> bool:
    try:
        stream = client.create_stream(
            messages=[UserMessage(content="hi", source="user")],
            extra_create_args={"max_tokens": 4, "stream_options": {"include_usage": True}},
        )
        async for _ in stream: pass
        return True
    except Exception:
        return False

async def pick_ready_model(models: List[str]) -> OpenAIChatCompletionClient:
    for m in models:
        client = make_client(m)
        if await preflight(client):
            print(f"[preflight] Using model: {m}")
            return client
        print(f"[preflight] Model not ready: {m} -> next")
    raise RuntimeError("No model available.")

def _docker_exec(cmd: str, image: str = DOCKER_IMAGE) -> tuple[int, str, str]:
    workdir = os.path.abspath("sandbox"); os.makedirs(workdir, exist_ok=True)
    docker_cmd = (
        f"docker run --rm -v {workdir}:/workspace -w /workspace {image} "
        f"bash -lc {shlex.quote(cmd)}"
    )
    p = subprocess.run(docker_cmd, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr

async def docker_sh(*, command: str) -> str:
    code, out, err = _docker_exec(command, image=DOCKER_IMAGE)
    if code == 0: return (out or "").strip() or "(no output)"
    return f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

async def main():
    os.makedirs("sandbox", exist_ok=True)
    model = await pick_ready_model(PREFERRED_MODELS)

    exec_tool = PythonCodeExecutionTool(LocalCommandLineCodeExecutor(work_dir="sandbox"))
    planner = AssistantAgent("Planner", model_client=model)
    coder   = AssistantAgent("Coder",   model_client=model, tools=[exec_tool, docker_sh])
    tester  = AssistantAgent("Tester",  model_client=model, tools=[exec_tool, docker_sh])

    term = (TextMentionTermination(" passed in ")
            | TextMentionTermination("All tests passed")
            | MaxMessageTermination(MAX_TURNS))
    team = RoundRobinGroupChat([planner, coder, tester], termination_condition=term)

    task = """You are a team solving a tiny coding task.

STRICT RULES:
- Use ONLY the provided tools (Python execution & docker_sh). Do NOT emit <bash>, pseudo-XML, or code blocks as if they were executed.
- Keep messages short.

Goal:
1) Create in the sandbox:
   - sandbox/solution.py implementing sum_of_squares(nums: list[int]) -> int
   - sandbox/test_solution.py with pytest tests (normal + edge cases)
2) Run tests INSIDE a clean Docker container using docker_sh, exactly:
   - {"command":"python -m pip install -q pytest"}
   - {"command":"python -m pytest -q"}
Tester: after each test run, print ONLY the last non-empty line of pytest stdout (no extra text)."""

    t0 = time.time()
    result = await Console(team.run_stream(task=task))
    print(f"\n--- SUMMARY ---\nElapsed seconds: {time.time()-t0:.2f}")
    try: print(f"Messages exchanged: {len(result.messages)}")
    except: pass

if __name__ == "__main__":
    asyncio.run(main())
