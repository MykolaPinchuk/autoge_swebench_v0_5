# team_swebench_mvp_stopfix.py
# MVP multi-agent repo runner (clone/install/pytest) with robust termination.
# pip install -U autogen-agentchat autogen-ext[openai]
# docker build -f Dockerfile.swe -t swebench-lite:py3.10 .

import os, shlex, time, asyncio, subprocess, json, re
from datetime import datetime, timezone
from typing import List, Optional
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.ui import Console
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
from chutes_config import load_chutes_key, get_chutes_base_url
from swe_instance import load_instance, SWEInstance

# ---------------- config ----------------
CHUTES_API_KEY  = load_chutes_key()
CHUTES_BASE_URL = get_chutes_base_url()
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

# Optional SWE-bench instance override
INSTANCE_FILE = os.environ.get("SWE_INSTANCE_FILE", "").strip()
INSTANCE: Optional[SWEInstance] = None
if INSTANCE_FILE:
    try:
        INSTANCE = load_instance(INSTANCE_FILE)
        TARGET_REPO = INSTANCE.repo_url
        TARGET_REF = INSTANCE.ref
        PYTEST_K = INSTANCE.pytest_k
        print(f"[instance] Loaded: {INSTANCE.id} -> repo={TARGET_REPO} ref={TARGET_REF or '(default)'} -k=\"{PYTEST_K}\"")
    except Exception as e:
        raise SystemExit(f"Failed to load SWE instance from {INSTANCE_FILE}: {e}")

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

def _instrument_client(client: OpenAIChatCompletionClient, model_name: str) -> OpenAIChatCompletionClient:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    orig_create_stream = client.create_stream

    def _merge(u):
        try:
            get = (lambda k: (u.get(k) if isinstance(u, dict) else getattr(u, k, None)))
            pt = get("prompt_tokens") or get("input_tokens") or 0
            ct = get("completion_tokens") or get("output_tokens") or 0
            tt = get("total_tokens") or 0
            if isinstance(pt, int): totals["prompt_tokens"] += pt
            if isinstance(ct, int): totals["completion_tokens"] += ct
            if isinstance(tt, int) and tt:
                totals["total_tokens"] += tt
            else:
                totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
        except Exception:
            pass

    def wrapped_create_stream(*args, **kwargs):
        extra = kwargs.get("extra_create_args") or {}
        if not isinstance(extra, dict): extra = {}
        so = dict(extra.get("stream_options") or {})
        so["include_usage"] = True
        extra["stream_options"] = so
        kwargs["extra_create_args"] = extra
        stream = orig_create_stream(*args, **kwargs)
        async def gen():
            async for chunk in stream:
                u = getattr(chunk, "usage", None)
                if u: _merge(u)
                yield chunk
        return gen()

    client.create_stream = wrapped_create_stream  # type: ignore
    client._usage_totals = totals  # type: ignore
    client._selected_model_name = model_name  # type: ignore
    return client

async def pick_ready_model() -> OpenAIChatCompletionClient:
    for m in MODEL_CANDIDATES:
        c = make_client(m)
        if await preflight(c):
            print(f"[preflight] Using model: {m}")
            return _instrument_client(c, m)
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
        r = shlex.quote(ref)
        cmds.append(
            "cd project && "
            f"(git fetch --depth 1 origin {r} && git checkout -q {r}) "
            f"|| (git fetch --depth 50 origin {r} && git checkout -q {r}) "
            f"|| ((git fetch --unshallow origin || git fetch --unshallow || true) && git checkout -q {r})"
        )
    code, out, err = _docker(" && ".join(cmds))
    return "(cloned)" if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

async def swe_install(*, req_file: str = "requirements.txt") -> str:
    cmd = f"cd project && if [ -f {shlex.quote(req_file)} ]; then python -m pip install -q -r {shlex.quote(req_file)}; else echo 'no requirements.txt'; fi"
    code, out, err = _docker(cmd)
    return (out or "ok").strip() if code == 0 else f"(exit {code})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

async def swe_pytest(*, pytest_args: str = "-q") -> str:
    cmd = f"""
cd project
python - <<'PY'
import subprocess
try:
    import pytest  # noqa: F401
except Exception:
    subprocess.run('python -m pip install -q -U pytest', shell=True, check=False)
PY
python -m pytest {pytest_args}
"""
    code, out, err = _docker(cmd)
    # Return ONLY the last non-empty line of stdout; fallback to stderr
    def last_nonempty(s: str) -> str:
        lines = [ln for ln in (s or "").splitlines() if ln.strip()]
        return lines[-1] if lines else ""
    tail = last_nonempty(out) or last_nonempty(err) or ""
    # record tail for metrics only if non-empty
    global LAST_PYTEST_TAIL
    if tail:
        LAST_PYTEST_TAIL = tail
    # Always return the tail (success or not)
    return tail if tail else "no tests ran"

# ---------------- main ----------------
async def main():
    model = await pick_ready_model()

    planner = AssistantAgent("Planner", model_client=model)
    coder   = AssistantAgent("Coder",   model_client=model, tools=[swe_clone, swe_install, swe_pytest])
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
    started = datetime.now(timezone.utc).isoformat()
    res = await Console(team.run_stream(task=task))
    elapsed = time.time()-t0
    ended = datetime.now(timezone.utc).isoformat()
    print(f"\n--- SUMMARY ---\nElapsed seconds: {elapsed:.2f}")
    try:
        print(f"Messages: {len(res.messages)}")
    except:
        pass

    # Metrics
    def infer_status(tail: str) -> str:
        s = (tail or "").lower()
        if not s:
            return "unknown"
        if re.search(r"\b\d+\s+passed\b", s) and not ("failed" in s or "error" in s or "errors" in s):
            return "pass"
        if "failed" in s or "error" in s or "errors" in s:
            return "fail"
        return "unknown"

    try:
        msg_count = len(res.messages)
    except Exception:
        msg_count = None

    usage = getattr(model, "_usage_totals", None)
    model_name = getattr(model, "_selected_model_name", None) or getattr(model, "model", None) or getattr(model, "_model", None)

    record = {
        "instance_id": (INSTANCE.id if INSTANCE else None),
        "repo_url": TARGET_REPO,
        "ref": TARGET_REF,
        "pytest_k": PYTEST_K,
        "model": model_name,
        "team": "planner-coder-tester",
        "start_ts": started,
        "end_ts": ended,
        "elapsed_sec": round(elapsed, 3),
        "messages": msg_count,
        "final_pytest_tail": globals().get("LAST_PYTEST_TAIL", None),
        "status": infer_status(globals().get("LAST_PYTEST_TAIL", "") or ""),
        "tokens": (
            {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }
            if isinstance(usage, dict)
            else None
        ),
    }

    try:
        os.makedirs("sandbox", exist_ok=True)
        with open(os.path.join("sandbox", "results.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"(metrics write failed): {e}")

if __name__ == "__main__":
    asyncio.run(main())
