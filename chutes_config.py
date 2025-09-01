"""
Centralized Chutes configuration.

Provides a zero-maintenance loader for CHUTES_API_KEY that:
- Returns CHUTES_API_KEY from the environment if present.
- Otherwise reads it from a local file (default: chutes_key.txt next to this file),
  sets it in os.environ for the current process, and returns it.

This avoids hard-coding keys in code and avoids shell wrappers.
"""

from __future__ import annotations

import os
import json
import re
from pathlib import Path


DEFAULT_KEY_FILENAME = "chutes_key.txt"
ENV_VAR = "CHUTES_API_KEY"


def _default_key_path(filename: str = DEFAULT_KEY_FILENAME) -> Path:
    # Resolve relative to this file's directory to be robust to CWD changes.
    here = Path(__file__).resolve().parent
    return here / filename


def _parse_key_text(text: str) -> str:
    """Extract an API key from various simple formats.

    Supported:
    - raw token (optionally quoted)
    - key=value, api_key = "value"
    - JSON like {"api_key": "value"} or {"key": "value"}
    """
    s = (text or "").strip()
    if not s:
        return ""
    # Try JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            for k in ("api_key", "key", "token"):
                v = obj.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().strip('"\'')
    except Exception:
        pass

    # Single-line heuristics: take first non-empty, non-comment line
    for line in s.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # key=value pattern
        if "=" in line:
            val = line.split("=", 1)[1].strip()
            return val.strip().strip('"\'')
        # explicit token pattern (starts with cpk_)
        m = re.search(r"cpk_[A-Za-z0-9._-]+", line)
        if m:
            return m.group(0)
        # fallback: strip surrounding quotes
        return line.strip().strip('"\'')
    return ""


def load_chutes_key(filename: str = DEFAULT_KEY_FILENAME, env_var: str = ENV_VAR) -> str:
    """
    Ensure CHUTES_API_KEY is present. If not found in env, read from a local file
    and set it in os.environ for this process. Returns the key string.

    Raises FileNotFoundError if neither the env var nor the file is available.
    """
    key = os.environ.get(env_var)
    if key:
        return key

    key_path = _default_key_path(filename)
    if not key_path.exists():
        raise FileNotFoundError(
            f"{env_var} not set and key file not found at: {key_path}"
        )

    raw = key_path.read_text(encoding="utf-8")
    key = _parse_key_text(raw)
    if not key:
        raise ValueError(f"Key file {key_path} is empty")

    os.environ[env_var] = key
    return key


def get_chutes_base_url(default: str = "https://llm.chutes.ai/v1") -> str:
    return os.environ.get("CHUTES_BASE_URL", default)
