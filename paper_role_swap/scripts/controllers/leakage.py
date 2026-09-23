"""Fail closed if model input contains forbidden truth/forensic fields."""
from __future__ import annotations

import json
import re
from typing import Any

FORBIDDEN_FIELDS = (
    "truth",
    "ground_truth",
    "correct",
    "incorrect",
    "rescued",
    "known_error",
    "posthoc",
    "post_hoc",
)

_TOKEN_RE = re.compile(
    r"\b(truth|ground_truth|correct|incorrect|rescued|known_error|posthoc|post_hoc)\b",
    re.IGNORECASE,
)


def _walk_keys(obj: Any, found: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_FIELDS:
                found.append(str(key))
            _walk_keys(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_keys(item, found)


def serialized_input(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=str, separators=(",", ":"))


def assert_no_forbidden_fields(obj: Any, *, label: str) -> None:
    found_keys: list[str] = []
    _walk_keys(obj, found_keys)
    text = serialized_input(obj)
    tokens = sorted({m.group(1).lower() for m in _TOKEN_RE.finditer(text)})
    if found_keys or tokens:
        raise SystemExit(
            "STOP: forbidden truth/forensic field present in "
            f"{label}: keys={found_keys} tokens={tokens}"
        )
