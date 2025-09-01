from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SWEInstance:
    id: str
    repo_url: str
    ref: str
    pytest_k: str
    notes: str | None = None


def load_instance(path: str | Path) -> SWEInstance:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    required = ["id", "repo_url", "pytest_k"]
    for k in required:
        if k not in data or not isinstance(data[k], str) or not data[k].strip():
            raise ValueError(f"Invalid instance: missing or empty field '{k}' in {p}")
    return SWEInstance(
        id=data["id"].strip(),
        repo_url=data["repo_url"].strip(),
        ref=str(data.get("ref", "") or "").strip(),
        pytest_k=data["pytest_k"].strip(),
        notes=(data.get("notes") or None),
    )
