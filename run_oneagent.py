# run_oneagent.py
# One-agent MVP for repo validation in Docker with robust termination and quick debugging.

import os
import shlex
import time
import asyncio
import subprocess
from typing import List, Optional, Tuple

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console

from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from chutes_config import load_chutes_key, get_chutes_base_url

# ---------------- config ----------------
CHUTES_API_KEY = load_chutes_key()
CHUTES_BASE_URL = get_chutes_base_url()

# Default candidates; can be overridden via CHUTES_MODEL(S)
MODEL_CANDIDATES: List[str] = [
    "moonshotai/Kimi-K2-Instruct-75k",
    "openai/gpt-oss-120b",
    "deepseek-ai/DeepSeek-V3-0324",
    "openai/gpt-oss-20b",
    "deepseek-ai/DeepSeek-R1-0528",
    "Qwen/Qwen2.5-VL-32B-Instruct",
    "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    "unsloth/gemma-3-12b-it",
    "chutesai/Devstral-Small-2505",
    "zai-org/GLM-4.5-Air",
    "Qwen/Qwen3-14B",
]
BASE_MODEL_INFO = {
    "vision": False,
    "function_calling": True,
    "json_output": False,
    "structured_output": False,
    "family": "unknown",
}

DOCKER_IMAGE = os.environ.get("SWE_IMAGE", "swebench-lite:py3.10")
MAX_TURNS = 4  # small cap—should finish in ~3 messages

TARGET_REPO = os.environ.get("TARGET_REPO", "https://github.com/pytest-dev/pytest")
TARGET_REF = os.environ.get("TARGET_REF", "")
PYTEST_K = os.environ.get("PYTEST_K", "collection")  # example; set "" to run all tests


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
        async for _ in stream:
            pass
        return True
    except Exception:
        return False


def _get_candidate_models() -> List[str]:
    # Allow override via env: CHUTES_MODEL or CHUTES_MODELS (comma-separated)
    single = os.environ.get("CHUTES_MODEL")
    if single and single.strip():
        return [single.strip()]
    multi = os.environ.get("CHUTES_MODELS")
    if multi and multi.strip():
        return [m.strip() for m in multi.split(",") if m.strip()]
    return MODEL_CANDIDATES


async def pick_ready_model() -> OpenAIChatCompletionClient:
    for m in _get_candidate_models():
        c = make_client(m)
        if await preflight(c):
            print(f"[preflight] Using model: {m}")
            return c
        print(f"[preflight] Model not ready: {m} -> next")
    raise RuntimeError("No model available for now.")


# ---------------- docker helpers ----------------
def _docker(cmd: str) -> Tuple[int, str, str]:
    workdir = os.path.abspath("sandbox")
    os.makedirs(workdir, exist_ok=True)
    full = f"docker run --rm -v {workdir}:/workspace -w /workspace {DOCKER_IMAGE} bash -lc {shlex.quote(cmd)}"
    p = subprocess.run(full, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


# ---- tools (async functions with type hints) ----
async def swe_clone(*, repo_url: str, ref: Optional[str] = None) -> str:
    cmds = [f"rm -rf project && git clone --depth 1 {shlex.quote(repo_url)} project"]
    if ref:
        cmds.append(
            f"cd project && git fetch --depth 1 origin {shlex.quote(ref)} && git checkout -q {shlex.quote(ref)}"
        )
    code, out, err = _docker(" && ".join(cmds))
    return "(cloned)" if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"


async def swe_install(*, req_file: str = "requirements.txt") -> str:
    cmd = (
        f"cd project && "
        f"if [ -f {shlex.quote(req_file)} ]; then python -m pip install -q -r {shlex.quote(req_file)}; "
        f"else echo 'no requirements.txt'; fi"
    )
    code, out, err = _docker(cmd)
    return (out or "ok").strip() if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"


async def swe_pytest(*, pytest_args: str = "-q") -> str:
    cmd = f"""
cd project
python - <<'PY'
import sys, subprocess
try:
    import pytest  # noqa: F401
except Exception:
    subprocess.run('python -m pip install -q -U pytest', shell=True, check=False)
PY
python -m pytest {pytest_args}
"""
    code, out, err = _docker(cmd)
    # Return ONLY the last non-empty line of stdout; fallback to stderr; else simple message
    def last_nonempty(s: str) -> str:
        lines = [ln for ln in (s or "").splitlines() if ln.strip()]
        return lines[-1] if lines else ""

    tail = last_nonempty(out) or last_nonempty(err) or "no tests ran"
    return tail


# ---------------- main ----------------
async def main():
    model = await pick_ready_model()

    # One agent with the tools
    runner = AssistantAgent("Runner", model_client=model, tools=[swe_clone, swe_install, swe_pytest])

    # Robust termination: catch typical pytest tails (pass/fail/error/summary variants)
    term = (
        TextMentionTermination(" passed in ")
        | TextMentionTermination(" passed")
        | TextMentionTermination(" failed")
        | TextMentionTermination(" error")
        | TextMentionTermination(" deselected")
        | TextMentionTermination(" skipped")
        | TextMentionTermination(" short test summary ")
        | TextMentionTermination(" no tests ran")
        | MaxMessageTermination(MAX_TURNS)
    )
    team = RoundRobinGroupChat([runner], termination_condition=term)

    # Build pytest args w/ clean quoting
    kflag = f'-k "{PYTEST_K}"' if PYTEST_K else ""
    pytest_args = f"-q {kflag}".strip()

    task = f"""Validate a Python repo in Docker. Execute EXACTLY these three tool calls, then STOP.
Do NOT print tool call syntax, XML/angle-bracket markup, or explanations. Paste only tool returns when prompted.

1) swe_clone(repo_url="{TARGET_REPO}", ref="{TARGET_REF}")
2) swe_install()
3) swe_pytest(pytest_args="{pytest_args}")

CRITICAL OUTPUT RULE:
After step 3, print ONLY the exact string returned by swe_pytest (the last non-empty pytest stdout line). No extra words.
"""

    t0 = time.time()
    res = await Console(team.run_stream(task=task))
    print(f"\n--- SUMMARY ---\nElapsed seconds: {time.time() - t0:.2f}")
    try:
        print(f"Messages: {len(res.messages)}")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
