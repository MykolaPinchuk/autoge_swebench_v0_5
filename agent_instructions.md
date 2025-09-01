## Agent instructions (read me before you act)

Scope
- Stay within this repository. Do not access external network resources or other local folders.
- Prefer minimal, targeted actions that keep logs clean and reproducible.
- Do not overengineer.
- Keep in mind the big picture of this project.

General output rules
- Keep messages concise. Avoid verbose explanations.
- Do not emit the literal word "TERMINATE" unless explicitly requested.
- When running tests, paste ONLY the last non‑empty line of pytest stdout (no extra words).

Paths and environment
- Local sandbox folder: `sandbox/`
	- Repo clones (inside Docker) live at `sandbox/project/` and map to `/workspace/project` in the container.
	- You can write scratch files in `sandbox/`.
- Do not write outside this repo.

Tools you may be offered (repo validation flows)
- swe_clone(repo_url: str, ref: str|None): Clone target repo into `/workspace/project`.
- swe_install(req_file: str = "requirements.txt"): Install deps if file exists.
- swe_pytest(pytest_args: str = "-q"): Run pytest; you must return ONLY the final stdout line.

If you receive these tools, follow this exact sequence and stop:
1) swe_clone(...)
2) swe_install()
3) swe_pytest(...)
Then print only the returned line from step 3.

Local tiny coding loop (when asked to create code + tests)
- Implement function(s) in `sandbox/solution.py`.
- Create tests in `sandbox/test_solution.py` using pytest.
- Use Python file I/O to write files; then run `python -m pytest -q`.
- After each run, paste ONLY the last non‑empty line of pytest stdout.

Do / Don’t
- Do explain very briefly what you will do before running tools; then paste tool outputs verbatim.
- Do narrow pytest with `-k <expr>` if explicitly instructed for speed.
- Don’t invent file paths or change folders outside `sandbox/`.
- Don’t print tool invocation syntax or XML/angle‑bracket markup—only the tool return values.

Success signals (examples of tails)
- "X passed in Ys"
- "X passed"
- "X failed", "X errors" (failure is still a valid outcome to report)
