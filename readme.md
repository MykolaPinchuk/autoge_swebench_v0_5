## DEMAS POC: Minimal multi‑agent + SWE‑bench repo runner

This repo is a tiny, pragmatic proof‑of‑concept that exercises core building blocks for Dynamic Evolutionary Multi‑Agent Systems (DEMAS):
- Run one or more LLM agents using an OpenAI‑compatible API (Chutes.ai).
- Validate real open‑source repos inside Docker (clone → install → pytest) with robust tails and simple logs.
- Keep the workflow minimal for fast debugging and iteration.

### What’s inside

- `run_oneagent.py` — One‑agent MVP that clones a target repo in Docker and runs pytest, returning the last stdout line for easy termination.
- `team_swebench_mvp.py` — Small multi‑agent variant (Planner/Coder/Tester) orchestrating the same repo validation steps.
- `repo_validate.py` — Non‑agent script to run clone/install/pytest directly in Docker with log capture.
- `team_min_chutes_v2.py` — Minimal coding loop using a local Python execution tool (writes files in `sandbox/` and runs pytest).
- `chutes_config.py` — Centralized loader for `CHUTES_API_KEY` (env‑first, else `chutes_key.txt` with flexible parsing) and base URL.
- `Dockerfile.swe` — Thin image used to run tests in isolation (Python 3.10 + git and pip flow).
- `sandbox/` — Workspace bind‑mounted into the container; includes `project/` (cloned repo) and saved logs on failure.

### Current repo structure (top level)

```
.
├─ Dockerfile.swe
├─ chutes_config.py
├─ chutes_key.txt           # not tracked; local only (ignored by .gitignore/.dockerignore)
├─ requirements.txt         # local env (autogen libs, pytest)
├─ run_oneagent.py          # one‑agent SWE‑bench‑style runner
├─ team_swebench_mvp.py     # multi‑agent variant
├─ repo_validate.py         # direct runner (no agents)
├─ team_min_chutes_v2.py    # tiny coding task loop (local exec tool)
├─ run_multiagent.py        # convenience wrapper for team_swebench_mvp
├─ local_task.py            # convenience wrapper for team_min_chutes_v2
├─ sandbox/                 # bind mount workspace; stores logs and cloned repos
│  ├─ project/              # cloned target repository
│  ├─ last_run_stdout.log   # saved on failures by repo_validate.py
│  └─ last_run_stderr.log   # saved on failures by repo_validate.py
└─ readme.md
```

### Setup

1) Python venv and dependencies (local):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

2) Chutes API key: put your key in environment or create `chutes_key.txt` (the loader accepts raw token, `api_key="..."`, `key=value`, or JSON). Example:

```bash
export CHUTES_API_KEY="cpk_..."        # or place it in chutes_key.txt
export CHUTES_BASE_URL="https://llm.chutes.ai/v1"  # default
```

3) Build the Docker image used for testing (once):

```bash
docker build -t swebench-lite:py3.10 -f Dockerfile.swe .
```

### How to run

Option A — One‑agent repo validation (recommended first run):

```bash
# Optional overrides
export TARGET_REPO="https://github.com/pytest-dev/pytest"
export TARGET_REF=""                 # branch/tag/commit; empty for default
export PYTEST_K="collection"         # pytest -k expression; empty to run all
export CHUTES_MODEL="moonshotai/Kimi-K2-Instruct-75k"   # or set CHUTES_MODELS as CSV

python -u run_oneagent.py
```

What you’ll see: the agent will preflight a model, then run three tools in Docker: clone, install (if `requirements.txt` exists), and pytest. It prints only the final pytest stdout line (e.g., `3387 deselected, 3 errors in 2.97s`). Pytest is auto‑installed in the container if missing.

Option B — Multi‑agent MVP (Planner/Coder/Tester):

```bash
python -u run_multiagent.py
```

Option C — Direct runner (no agents), with logs on failure:

```bash
python -u repo_validate.py https://github.com/pytest-dev/pytest collection
```

Option D — Tiny local coding loop (writes to `sandbox/` and runs pytest locally):

```bash
python -u local_task.py
```

### Notes

- The container runs in `/workspace` with your local `sandbox/` bind‑mounted. Cloned repos live in `sandbox/project/`.
- If a target repo has no `requirements.txt`, the runner still executes pytest; some projects bootstrap via `pip install -e .` (see `repo_validate.py`).
- To change the Docker image, set `SWE_IMAGE` (default: `swebench-lite:py3.10`).
- For broader test runs, clear `PYTEST_K` to run all tests (can be slow on large repos).

### Troubleshooting

- “ModuleNotFoundError: autogen_…”: ensure the local venv is active and `pip install -r requirements.txt` ran.
- “No module named pytest” inside the container: the one‑agent runner will auto‑install pytest before running; for the direct runner, it installs pytest explicitly.
- Chutes auth issues: check `CHUTES_API_KEY` or `chutes_key.txt` format; JSON, `api_key=...`, or raw token are supported.

— Minimal by design. Tweak and extend as needed to explore DEMAS behaviors.

