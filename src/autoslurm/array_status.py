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
    tasks = {_array_task_index(job_id, key): state for key, state in raw_statuses.items()
             if _array_task_index(job_id, key) is not None}
    if (tasks or declared_total is not None) and exact in FAILED_STATES:
        return "CANCELLED" if exact == "CANCELLED" else "FAILED"
    states = list(tasks.values())
    if not states:
        if declared_total is not None and exact == "COMPLETED":
            return "UNKNOWN"
        return exact or "UNKNOWN"
    if declared_total is not None and len(states) < declared_total:
        states.append("UNKNOWN")
    state = aggregate_states(states)
    if state == "UNKNOWN" and exact not in {None, "COMPLETED"}:
        return exact
    return state


def aggregate_states(states):
    """Conservative common state: completion requires every expected observation."""
    upper = [str(state).upper() for state in states]
    if "CANCELLED" in upper:
        return "CANCELLED"
    if any(state in FAILED_STATES for state in upper):
        return "FAILED"
    if any(state in RUNNING_LIKE_STATES for state in upper):
        return "RUNNING"
    if "PENDING" in upper:
        return "PENDING"
    if upper and all(state == "COMPLETED" for state in upper):
        return "COMPLETED"
    return "UNKNOWN"


def array_progress_for_job_id(
    job_id: str,
    raw_statuses: dict[str, str],
    declared_total: int | None = None,
) -> tuple[bool, int, int]:
    """
    Return (is_array, n_completed, n_array) for a job id based on task entries.
    """
    tasks = {_array_task_index(job_id, key): state for key, state in raw_statuses.items()
             if _array_task_index(job_id, key) is not None}
    if not tasks and declared_total is None:
        return False, 0, 0
    return True, sum(state.upper() == "COMPLETED" for state in tasks.values()), declared_total if declared_total is not None else len(tasks)


def declared_array_size(array_spec: str | None) -> int | None:
    """
    Parse a Slurm --array spec and return total task count.
    Supports forms like:
    - "1-10"
    - "1-10%6"
    - "1-10:2"
    - "1,3,5-9"
    """
    indices = declared_array_indices(array_spec)
    return len(indices) if indices is not None else None


def declared_array_indices(array_spec: str | None) -> list[int] | None:
    """
    Parse a Slurm --array spec and return the concrete task indices.
    Supports the same forms as declared_array_size.
    """
    if array_spec is None:
        return None
    text = str(array_spec).strip()
    if not text:
        return None
    text = text.split("%", 1)[0].strip()
    if not text:
        return None

    indices: list[int] = []
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
            indices.extend(range(start, end + 1, step))
            continue

        if re.fullmatch(r"-?\d+", part):
            indices.append(int(part))
            continue
        return None

    return sorted(set(indices)) if indices and all(index >= 0 for index in indices) else None


def _array_task_index(job_id: str, raw_job_id: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(job_id)}[_.](\d+)", str(raw_job_id))
    if match is None:
        return None
    return int(match.group(1))


def canonical_job_id(value):
    """Keep task indices; drop scheduler steps rather than treating them as tasks."""
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)(?:[_.](\d+))?", text)
    if not match:
        return None
    return match[1] + ("_" + str(int(match[2])) if match[2] is not None else "")


def parent_job_id(value):
    """Validate a scheduler parent identity before it joins a query batch."""
    text = str(value)
    return text if re.fullmatch(r"\d+", text) else None
