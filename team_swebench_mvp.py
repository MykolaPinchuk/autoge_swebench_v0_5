# team_swebench_mvp_stopfix.py
# MVP multi-agent repo runner (clone/install/pytest) with robust termination.
# pip install -U autogen-agentchat autogen-ext[openai]
# docker build -f Dockerfile.swe -t swebench-lite:py3.10 .

import os, shlex, time, asyncio, subprocess
from typing import List, Optional
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

# ---------------- config ----------------
CHUTES_API_KEY  = os.environ.get("CHUTES_API_KEY",  "cpk_6409376b53ff4bcda0bed0b6e71b2abe.105ceb10f63a5052bf24ac406ffcf330.9IVsa2JTvSIgVL1nUCSOCfOpBlKvcust")
CHUTES_BASE_URL = os.environ.get("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
MODEL_CANDIDATES: List[str] = [
    "moonshotai/Kimi-K2-Instruct-75k",
    "openai/gpt-oss-120b",
    "deepseek-ai/DeepSeek-V3-0324",
    "openai/gpt-oss-20b",
]
BASE_MODEL_INFO = {"vision": False, "function_calling": True, "json_output": False, "structured_output": False, "family": "unknown"}
DOCKER_IMAGE    = os.environ.get("SWE_IMAGE", "swebench-lite:py3.10")
MAX_TURNS       = 10  # tight cap to avoid ping-pong

TARGET_REPO = os.environ.get("TARGET_REPO", "https://github.com/pytest-dev/pytest")
TARGET_REF  = os.environ.get("TARGET_REF", "")
PYTEST_K    = os.environ.get("PYTEST_K", "")  # optional -k expression

# ------------- model + preflight -------------
def make_client(model_name: str) -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=model_name,
        api_key=CHUTES_API_KEY,
        base_url=CHUTES_BASE_URL,
        temperature=0.2,
        include_name_in_message=True,
        model_info=BASE_MODEL_INFO,
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

async def pick_ready_model() -> OpenAIChatCompletionClient:
    for m in MODEL_CANDIDATES:
        c = make_client(m)
        if await preflight(c):
            print(f"[preflight] Using model: {m}")
            return c
        else:
            print(f"[preflight] Model not ready: {m} -> next")
    raise RuntimeError("No model available for now.")

# ---------------- docker helpers ----------------
def _docker(cmd: str) -> tuple[int, str, str]:
    workdir = os.path.abspath("sandbox"); os.makedirs(workdir, exist_ok=True)
    full = f"docker run --rm -v {workdir}:/workspace -w /workspace {DOCKER_IMAGE} bash -lc {shlex.quote(cmd)}"
    p = subprocess.run(full, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr

# ---- tools (must be async functions with type hints) ----
async def swe_clone(*, repo_url: str, ref: Optional[str] = None) -> str:
    cmds = [f"rm -rf project && git clone --depth 1 {shlex.quote(repo_url)} project"]
    if ref:
        cmds.append(f"cd project && git fetch --depth 1 origin {shlex.quote(ref)} && git checkout -q {shlex.quote(ref)}")
    code, out, err = _docker(" && ".join(cmds))
    return "(cloned)" if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

async def swe_install(*, req_file: str = "requirements.txt") -> str:
    cmd = f"cd project && if [ -f {shlex.quote(req_file)} ]; then python -m pip install -q -r {shlex.quote(req_file)}; else echo 'no requirements.txt'; fi"
    code, out, err = _docker(cmd)
    return (out or "ok").strip() if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

async def swe_pytest(*, pytest_args: str = "-q") -> str:
    cmd = f"cd project && python -m pytest {pytest_args}"
    code, out, err = _docker(cmd)
    # Always return ONLY the last non-empty line of stdout (termination keys rely on it)
    last = [ln for ln in (out or "").splitlines() if ln.strip()]
    tail = last[-1] if last else ""
    if code == 0:
        return tail
    # On failure, still return the last line plus a short note
    return f"{tail if tail else '(no stdout)'}"

# ---------------- main ----------------
async def main():
    model = await pick_ready_model()

    planner = AssistantAgent("Planner", model_client=model)
    coder   = AssistantAgent("Coder",   model_client=model, tools=[swe_clone, swe_install])
    tester  = AssistantAgent("Tester",  model_client=model, tools=[swe_pytest])

    # Robust termination:
    # - pytest typical success: "X passed in Ys"
    # - some envs/plugins: "X passed" (no timing)
    # - model summaries: "All tests passed"
    # - hard cap
    term = (
        TextMentionTermination(" passed in ")
        | TextMentionTermination(" passed")
        | TextMentionTermination("All tests passed")
        | MaxMessageTermination(MAX_TURNS)
    )
    team = RoundRobinGroupChat([planner, coder, tester], termination_condition=term)

    kline = f'-k "{PYTEST_K}"' if PYTEST_K else ""
    task = f"""You are a team validating a Python repo inside Docker.

Tools (call them and paste ONLY tool output; do not paraphrase):
- swe_clone(repo_url, ref) -> clones into /workspace/project
- swe_install(req_file="requirements.txt") -> installs deps if file exists
- swe_pytest(pytest_args="-q") -> runs pytest and returns ONLY the last non-empty stdout line

Goal:
1) Clone:
   repo_url = {TARGET_REPO}
   ref      = {TARGET_REF or "(default)"}
2) Install dependencies.
3) Run tests with: -q {kline}
4) If tests fail, re-run with a narrower -k or briefly suggest next steps (but do not edit code in this MVP).
After each test run, paste ONLY the exact line returned by swe_pytest (no extra words).
"""

    t0 = time.time()
    res = await Console(team.run_stream(task=task))
    print(f"\n--- SUMMARY ---\nElapsed seconds: {time.time()-t0:.2f}")
    try:
        print(f"Messages: {len(res.messages)}")
    except:
        pass

if __name__ == "__main__":
    asyncio.run(main())
