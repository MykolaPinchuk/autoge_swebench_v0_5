## Handoff for the next agent

Context: This repo is a minimal DEMAS-style runner that clones a target OSS repo, installs deps, and runs pytest inside Docker, driven by one- or multi-agent orchestrations via an OpenAI-compatible API.

What works now
- One-agent and multi-agent flows on a lightweight target (pytest) run end-to-end.
- Instance-driven config: set `SWE_INSTANCE_FILE` to a JSON instance.
- Results are appended to `sandbox/results.jsonl` with: instance_id, model, team, timestamps, elapsed_sec, messages, pytest tail, status, and tokens (if available).
- Eval helpers:
  - `eval_run.py` runs one/team for a given instance and can sweep models via `CHUTES_MODELS`.
  - `eval_summary.py` prints a compact table from results.jsonl (supports FILTER_* envs).

Known gaps / next tasks
1) Improve install step (inside Docker) for heavy repos like pandas/numpy:
   - Try `pip install -e .` in `sandbox/project`.
   - If `extras_require` includes `test` or `dev`, attempt `pip install -e .[test]`.
   - Fallback to `-r requirements.txt` and ensure pytest present.
   - This logic should be added to the agent tool `swe_install` in both `run_oneagent.py` and `team_swebench_mvp.py`.
2) Re-run `swe_instances/example_pandas_fast.json` to confirm imports and basic tests run.
3) If compiled deps still block progress, consider a fuller Docker base with scientific wheels preinstalled.
4) Extend `eval_summary.py` with simple aggregates and optional `--csv` export.
5) Add brief README usage snippets for eval runner and results filtering (added below).

Quick start for the next session
- Ensure local venv is active and dependencies installed: `pip install -r requirements.txt`.
- Build the test image once: `docker build -t swebench-lite:py3.10 -f Dockerfile.swe .`.
- Run a quick sanity check on pytest instance:
  - `python eval_run.py one swe_instances/example_pytest.json`
- View results: `python eval_summary.py`.

Instances
- `swe_instances/example_pytest.json`: runs on pytest (`-k collection`).
- `swe_instances/example_pandas_fast.json`: narrow subset; currently fails on numpy import in the thin image.
- `swe_instances/example_numpy_fast.json`: similar caveat as pandas.

Notes
- Token usage is captured when the provider reports it during streaming; otherwise totals remain 0.
- The last non-empty pytest stdout line is used as the correctness signal and also printed by the one-agent path.
