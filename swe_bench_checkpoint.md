## SWE‑Bench Checkpoint

### 1) High‑level plan

We’re building a minimal evaluation harness for SWE‑Bench problems (real GitHub issues/PRs as software engineering tasks). Goals:

- Run a coding agent (AutoGen + Chutes OpenAI‑compatible API) to attempt a SWE‑Bench task.
- Execute everything inside a controlled Docker container (Python 3.10 image).
- Workflow inside the container:
	- Clone target repo at the specified commit from the SWE‑Bench instance.
	- Apply edits/patches.
	- Run pytest to validate correctness.
	- Collect signals: pass/fail, timing, usage if available.
- Grow scope: single easy task → a few pandas/numpy tasks → a small SWE‑Bench subset.

### 2) Context and environment

- Docker image: `swebench-lite:py3.10` (Python 3.10 + git), mount point `/workspace` bound to local `sandbox/`.
- Agents: AutoGen AssistantAgent(s). We use simple “tools” that shell out to Docker via `swe_clone`, `swe_install`, `swe_pytest`.
- LLM provider: Chutes.ai via OpenAI‑compatible client. Key management via `chutes_config.py` (env‑first or `chutes_key.txt`).
- Dataset: SWE‑Bench provides repo URLs, commits, and tests. Initial focus: pandas/numpy items for faster cycles.
- Validation steps (minimal): clone → install → pytest (optionally narrowed with `-k`).

Key scripts in this repo:

- `run_oneagent.py`: one‑agent MVP that performs the full Docker flow and prints the last pytest stdout line.
- `team_swebench_mvp.py`: small multi‑agent variant (Planner/Coder/Tester) orchestrating the same steps.
- `repo_validate.py`: direct runner (no agents) with helpful logs on failure.

### 3) Built so far (status)

- Docker image built and used successfully (`swebench-lite:py3.10`).
- Repo runners clone/install/pytest end‑to‑end against real repos (e.g., `pytest-dev/pytest`).
	- Auto‑install of `pytest` inside the container when missing (one‑agent path).
	- Log capture and tails for quick triage (`repo_validate.py`).
- Agents validated:
	- Multi‑agent loop (Planner/Coder/Tester) can run the Docker tools and detect success by pytest tails.
	- One‑agent runner is stable with strict instructions and termination.
- Secrets: centralized `CHUTES_API_KEY` loader; supports env/`chutes_key.txt` with flexible formats.

### 4) Next steps (SWE‑Bench integration)

1. Add a small loader for SWE‑Bench instance metadata (repo URL, commit/ref, pytest cmd/`-k`).
2. Wire the loader into `run_oneagent.py` (or `team_swebench_mvp.py`) to parameterize clone/ref and test args.
3. Start with one pandas/numpy task:
	 - Checkout the correct commit.
	 - Apply the solution patch (if provided or inferred by the agent).
	 - Run tests → confirm green.
4. Scale to a handful of tasks; collect simple metrics (success rate, elapsed time, usage if available).

### 5) Notes and conventions

- Docker caching: reuse `swebench-lite:py3.10` when possible.
- Repo location inside container: `/workspace/project` (maps to local `sandbox/project`).
- Execution tools exposed to agents: `swe_clone`, `swe_install`, `swe_pytest`.
- Termination: rely on pytest tails (e.g., `X passed in Ys`). Avoid emitting artificial “TERMINATE” strings.
- Starting points in this repo: `run_oneagent.py` (simplest), `team_swebench_mvp.py` (multi‑agent), `repo_validate.py` (no agents, logs).

First target: pick a pandas/numpy SWE‑Bench case (small runtime footprint) to validate the full cycle.