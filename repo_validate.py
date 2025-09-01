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
        print("Usage: python repo_validate.py <repo_url> [k_expr]\n"
              "Example: python repo_validate.py https://github.com/pytest-dev/pytest collection")
        raise SystemExit(2)

    repo_url = sys.argv[1]
    k_expr   = sys.argv[2] if len(sys.argv) >= 3 else ""
    kflag    = f'-k "{k_expr}"' if k_expr else ""

    code, out, err = run(f"rm -rf project && git clone --depth 1 {shlex.quote(repo_url)} project")
    if code != 0:
        print("CLONE FAILED"); print(tail(err) or err.strip()); raise SystemExit(1)

    combined = f"""
set -e
python -m pip install -q -U pip
cd project
python -m pip install -q hatchling hatch-vcs
python -m pip install -q -e .
python - <<'PY'
import subprocess
subprocess.run("python -m pip install -q -e .[dev]", shell=True, check=False)
PY
if [ -f testing/requirements.txt ]; then python -m pip install -q -r testing/requirements.txt; fi
python -m pip install -q -U pytest
python -m pytest -q {kflag}
"""
    code, out, err = run(combined)
    last = tail(out) or tail(err) or "(no output)"
    print(last)
    if code != 0:
        os.makedirs(WORKDIR, exist_ok=True)
        log_out = os.path.join(WORKDIR, "last_run_stdout.log")
        log_err = os.path.join(WORKDIR, "last_run_stderr.log")
        try:
            with open(log_out, "w", encoding="utf-8", errors="ignore") as f:
                f.write(out or "")
            with open(log_err, "w", encoding="utf-8", errors="ignore") as f:
                f.write(err or "")
        except Exception:
            pass
        print("\n--- pytest stdout (tail) ---\n" + "\n".join((out or "").splitlines()[-80:]))
        if err and err.strip():
            print("\n--- pytest stderr (tail) ---\n" + "\n".join((err or "").splitlines()[-80:]))
        print(f"\nFull logs saved to: {log_out}, {log_err}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
