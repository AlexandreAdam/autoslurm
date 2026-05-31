from __future__ import annotations

import re

FAILED_STATES = {
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
    "REVOKED",
}

RUNNING_LIKE_STATES = {
    "RUNNING",
    "COMPLETING",
    "CONFIGURING",
    "STAGE_OUT",
    "RESIZING",
    "REQUEUED",
    "SUSPENDED",
    "SIGNALING",
}
PENDING_LIKE_STATES = {
    "PENDING",
}


def status_for_job_id(
    job_id: str,
    raw_statuses: dict[str, str],
    declared_total: int | None = None,
) -> str:
    """
    Resolve a coherent status for a job id.

    For array parents, aggregate task statuses from entries like `12345_7`.
    Non-array jobs keep exact previous behavior.
    """
    exact = raw_statuses.get(job_id)
    task_prefix = f"{job_id}_"
    task_states = [state for key, state in raw_statuses.items() if key.startswith(task_prefix)]
    if not task_states:
        return exact or "UNKNOWN"

    task_upper = [state.upper() for state in task_states]
    if any(state == "CANCELLED" for state in task_upper):
        return "CANCELLED"
    if any(state in FAILED_STATES for state in task_upper):
        return "FAILED"
    total = declared_total if declared_total is not None else len(task_upper)
    completed = sum(1 for state in task_upper if state == "COMPLETED")
    if total > 0 and completed >= total and all(state == "COMPLETED" for state in task_upper):
        return "COMPLETED"
    if any(state == "RUNNING" for state in task_upper):
        return "RUNNING"
    if any(state in RUNNING_LIKE_STATES for state in task_upper):
        return "RUNNING"
    if declared_total is not None and 0 < completed < total:
        if exact and exact.upper() in PENDING_LIKE_STATES:
            return "PENDING"
        return "RUNNING"
    if any(state in PENDING_LIKE_STATES for state in task_upper):
        return "PENDING"
    return exact or "UNKNOWN"


def array_progress_for_job_id(
    job_id: str,
    raw_statuses: dict[str, str],
    declared_total: int | None = None,
) -> tuple[bool, int, int]:
    """
    Return (is_array, n_completed, n_array) for a job id based on task entries.
    """
    task_prefix = f"{job_id}_"
    task_states = [state for key, state in raw_statuses.items() if key.startswith(task_prefix)]
    if not task_states and declared_total is None:
        return False, 0, 0
    completed = sum(1 for state in task_states if state.upper() == "COMPLETED")
    total = declared_total if declared_total is not None else len(task_states)
    return True, completed, total


def declared_array_size(array_spec: str | None) -> int | None:
    """
    Parse a Slurm --array spec and return total task count.
    Supports forms like:
    - "1-10"
    - "1-10%6"
    - "1-10:2"
    - "1,3,5-9"
    """
    if array_spec is None:
        return None
    text = str(array_spec).strip()
    if not text:
        return None
    text = text.split("%", 1)[0].strip()
    if not text:
        return None

    total = 0
    for chunk in text.split(","):
        part = chunk.strip()
        if not part:
            return None

        match = re.fullmatch(r"(-?\d+)-(-?\d+)(?::(\d+))?", part)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            step = int(match.group(3) or "1")
            if step <= 0 or end < start:
                return None
            total += ((end - start) // step) + 1
            continue

        if re.fullmatch(r"-?\d+", part):
            total += 1
            continue
        return None

    return total if total > 0 else None
