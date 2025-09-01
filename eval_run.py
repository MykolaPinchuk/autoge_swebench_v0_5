from __future__ import annotations

import os
import sys
import shlex
import subprocess
from typing import List

PYTHON = sys.executable
ROOT = os.path.dirname(os.path.abspath(__file__))


def get_models() -> List[str]:
    s = os.environ.get("CHUTES_MODELS", "").strip()
    if not s:
        m = os.environ.get("CHUTES_MODEL", "").strip()
        return [m] if m else []
    return [x.strip() for x in s.split(",") if x.strip()]


def run_once(agent: str, instance_file: str, model: str | None) -> int:
    env = os.environ.copy()
    env["SWE_INSTANCE_FILE"] = instance_file
    if model:
        env["CHUTES_MODEL"] = model
    cmd = [PYTHON, "-u", "run_oneagent.py" if agent == "one" else "run_multiagent.py"]
    print("RUN:", ("model=" + model if model else "model=(auto)"), "agent=", agent)
    return subprocess.call(cmd, cwd=ROOT, env=env)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("one", "team"):
        print("Usage: python eval_run.py <one|team> <instance.json>\n"
              "Optionally set CHUTES_MODELS=csv or CHUTES_MODEL to control model(s).")
        sys.exit(2)
    agent = sys.argv[1]
    instance_file = os.path.abspath(sys.argv[2])
    if not os.path.exists(instance_file):
        print(f"Instance not found: {instance_file}")
        sys.exit(2)

    models = get_models()
    if not models:
        # Run once with auto-picked model
        code = run_once(agent, instance_file, None)
        sys.exit(code)

    rc = 0
    for m in models:
        code = run_once(agent, instance_file, m)
        rc = rc or code
    sys.exit(rc)


if __name__ == "__main__":
    main()
