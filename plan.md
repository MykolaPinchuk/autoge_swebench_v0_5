# Plan: SWE-bench single-instance agent evaluation (pandas/numpy)

This plan moves from a generic repo validator to solving one SWE-bench task end-to-end and capturing basic evaluation metrics, in small, validated increments.

## Goals
- Solve one pandas/numpy SWE-bench problem with one agent (then extend to teams).
- Capture correctness, elapsed time, message/step count, and token usage.
- Keep changes minimal and validate after each step.

## Phase 1 — Instance loader (smallest change)
- Add a tiny SWE-bench instance format and loader.
- Wire it into the existing one-agent runner without changing core logic.

Deliverables
- swe_instances/example_pandas.json (sample instance) with fields:
  - id (str), repo_url (str), ref (str, commit/tag/branch or empty), pytest_k (str), notes (optional)
- swe_instance.py (loader)
- run_oneagent.py reads SWE_INSTANCE_FILE (env var); if set, overrides TARGET_REPO/TARGET_REF/PYTEST_K.

Validation
- Run run_oneagent.py with the example instance; ensure clone → install → pytest runs and prints only the final pytest line.
- Clear error if instance is missing/invalid.

## Phase 2 — Metrics capture (one-agent)
- Persist one JSONL record per run to sandbox/results.jsonl.

Fields
- instance_id, model, start_ts, end_ts, elapsed_sec
- messages (count), final_pytest_tail, exit_status
- Optional: repo_url, ref, pytest_k for traceability

Validation
- File created/appended with a well-formed JSON line after each run.

## Phase 3 — Token usage
- Enable include_usage on model streams and aggregate totals.
- Extend results with: prompt_tokens, completion_tokens, total_tokens (null if provider omits).

Validation
- Values appear in results for providers that return usage; otherwise nulls.

## Phase 4 — One pandas/numpy instance
- Add one concrete pandas/numpy instance targeting a narrow, fast subset via pytest -k.
- Robust git checkout: try shallow clone; on checkout failure, perform a fallback fetch (deepen or unshallow) and retry.

Validation
- End-to-end run completes with stored metrics and acceptable runtime.

## Phase 5 — Multi-agent parity
- Reuse the same instance loader and metrics recording in team_swebench_mvp.py.
- Add team metadata to results (team_type, members/roles).

Validation
- End-to-end run via run_multiagent.py records comparable metrics.

## Phase 6 — Model/team sweeps (basic)
- Allow CHUTES_MODELS (CSV) to iterate models sequentially, recording one result per model.
- Optional lightweight CLI wrapper (eval_one.py) to select instance + agent type and print a compact summary table from results.

Validation
- Sequential runs append multiple JSONL records; summary shows per-model metrics.

## Minimal instance schema (JSON)
{
  "id": "string",
  "repo_url": "string",
  "ref": "string",
  "pytest_k": "string",
  "notes": "optional string"
}

## Guardrails and notes
- Do not alter the core “only print the final pytest line” rule.
- Keep the one-agent path as the reference; multi-agent should be a drop-in with the same interfaces.
- Handle no requirements.txt gracefully (already supported).
- Token usage may be unavailable; treat as optional.

## Exit criteria for this milestone
- One pandas/numpy SWE-bench instance runs end-to-end with one agent.
- Results JSONL captures correctness signal (pytest tail), elapsed time, messages, and tokens (if available).
- Multi-agent path produces comparable records for the same instance.
