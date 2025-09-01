# repo_validate_docker_v5.py
# Clone -> editable install (+build backend) -> test deps -> ensure pytest -> run pytest (one container).
import os, sys, shlex, subprocess

DOCKER_IMAGE = os.environ.get("SWE_IMAGE", "swebench-lite:py3.10")
WORKDIR = os.path.abspath("sandbox")

def run(cmd: str):
    os.makedirs(WORKDIR, exist_ok=True)
    full = f"docker run --rm -v {WORKDIR}:/workspace -w /workspace {DOCKER_IMAGE} bash -lc {shlex.quote(cmd)}"
    p = subprocess.run(full, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr

def tail(s: str) -> str:
    lines = [ln for ln in (s or "").splitlines() if ln.strip()]
    return lines[-1] if lines else ""

def main():
    if len(sys.argv) < 2:
        print("Usage: python repo_validate_docker_v5.py <repo_url> [k_expr]\n"
              "Example: python repo_validate_docker_v5.py https://github.com/pytest-dev/pytest collection")
        raise SystemExit(2)

    repo_url = sys.argv[1]
    k_expr   = sys.argv[2] if len(sys.argv) >= 3 else ""
    kflag    = f'-k "{k_expr}"' if k_expr else ""

    # 1) fresh clone (persists on host volume)
    code, out, err = run(f"rm -rf project && git clone --depth 1 {shlex.quote(repo_url)} project")
    if code != 0:
        print("CLONE FAILED"); print(tail(err) or err.strip()); raise SystemExit(1)

    # 2) All installs + pytest run in ONE container to keep state:
    #    - upgrade pip
    #    - install build backend used by many modern projects (pytest uses hatchling + hatch-vcs)
    #    - editable install of the project itself
    #    - test requirements if present (pytest puts them in testing/requirements.txt)
    #    - ensure pytest is present/up-to-date
    #    - run pytest (optionally with -k)
    combined = f"""
set -e
python -m pip install -q -U pip
cd project
# Build backends commonly used by modern Python projects:
python -m pip install -q hatchling hatch-vcs
# Editable install of the project:
python -m pip install -q -e .
# Project-specific test deps (if present):
if [ -f testing/requirements.txt ]; then python -m pip install -q -r testing/requirements.txt; fi
# Ensure pytest itself is available/up-to-date:
python -m pip install -q -U pytest
# Run the tests:
python -m pytest -q {kflag}
"""
    code, out, err = run(combined)
    last = tail(out) or tail(err) or "(no output)"
    print(last)
    if code != 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
