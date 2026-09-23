"""Path guard: role-swap prediction runners must not read truth artifacts."""
from __future__ import annotations

FORBIDDEN_SUBSTRINGS = (
    "role_swap_cross_task/03_TRUTH",
    "role_swap_cross_task\\03_TRUTH",
    "ROLE_SWAP_TRUTH",
    "ROLE_SWAP_CANDIDATE_TRUTH",
)

ALLOWED_PREDICTION_INPUT = "role_swap_cross_task/02_CASES/ROLE_SWAP_PREDICTION_INPUT.csv"


def assert_prediction_path_allowed(path: str | bytes) -> None:
    text = path.decode() if isinstance(path, bytes) else str(path)
    norm = text.replace("\\", "/").lower()
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad.replace("\\", "/").lower() in norm:
            raise RuntimeError(f"STOP: prediction runner attempted to read truth path: {text}")
