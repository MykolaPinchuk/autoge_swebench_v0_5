from __future__ import annotations

import os
import json
import sys
from typing import Any, Dict, List

RESULTS = os.path.join("sandbox", "results.jsonl")


def read_results(path: str = RESULTS) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def fmt_tokens(t: Dict[str, Any] | None) -> str:
    if not isinstance(t, dict):
        return "-"
    return f"{int(t.get('total') or 0)}"


def summarize(rows: List[Dict[str, Any]]) -> str:
    # Columns: when, instance, team, model, status, elapsed, msgs, tokens
    header = [
        "end_ts",
        "instance_id",
        "team",
        "model",
        "status",
        "elapsed_sec",
        "messages",
        "tokens_total",
    ]
    out = ["\t".join(header)]
    for r in rows:
        out.append(
            "\t".join(
                [
                    str(r.get("end_ts", "")),
                    str(r.get("instance_id", "")),
                    str(r.get("team", "one-agent")),
                    str(r.get("model", "")),
                    str(r.get("status", "")),
                    str(r.get("elapsed_sec", "")),
                    str(r.get("messages", "")),
                    fmt_tokens(r.get("tokens")),
                ]
            )
        )
    return "\n".join(out)


def main():
    rows = read_results()
    if not rows:
        print("(no results)")
        return

    # Optional filters by env/args
    instance = os.environ.get("FILTER_INSTANCE")
    model = os.environ.get("FILTER_MODEL")
    team = os.environ.get("FILTER_TEAM")

    def keep(r: Dict[str, Any]) -> bool:
        if instance and str(r.get("instance_id")) != instance:
            return False
        if model and str(r.get("model")) != model:
            return False
        if team and str(r.get("team", "one-agent")) != team:
            return False
        return True

    rows = [r for r in rows if keep(r)]
    print(summarize(rows))


if __name__ == "__main__":
    main()
