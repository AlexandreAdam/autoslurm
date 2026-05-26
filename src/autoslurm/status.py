from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import Optional

from .save_load_jobs import latest_bundle_summaries, load_bundle
from .utils import load_config, ssh_host_from_config

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


def _parse_status_lines(text: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        job_id, state = line.split("|", 1)
        job_id = job_id.strip()
        state = state.strip()
        if not job_id or not state:
            continue
        statuses[job_id] = state.split()[0]
    return statuses


def _parse_job_field_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        job_id, value = line.split("|", 1)
        job_id = job_id.strip()
        value = value.strip()
        if not job_id or not value:
            continue
        values[job_id] = value
    return values


def _fetch_statuses_locally(job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    statuses: dict[str, str] = {}
    commands = (
        ["squeue", "-h", "-j", query, "-o", "%i|%T"],
        ["sacct", "-n", "-X", "-P", "-j", query, "-o", "JobIDRaw,State"],
    )
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        statuses.update(_parse_status_lines(result.stdout or result.stderr or ""))
    return statuses


def _fetch_statuses_remotely(
    job_ids: list[str], machine_name: str, machine_config: dict
) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    try:
        hostname = ssh_host_from_config(machine_config, machine_name)
    except AttributeError:
        return {}
    remote_script = "\n".join(
        [
            f"squeue -h -j {shlex.quote(query)} -o '%i|%T' 2>/dev/null || true",
            "printf '__AUTOSLURM_SPLIT__\\n'",
            f"sacct -n -X -P -j {shlex.quote(query)} -o JobIDRaw,State 2>/dev/null || true",
        ]
    )
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(remote_script)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    status_lines = (result.stdout or result.stderr or "").split("__AUTOSLURM_SPLIT__")
    statuses: dict[str, str] = {}
    for text in status_lines:
        statuses.update(_parse_status_lines(text))
    return statuses


def _fetch_statuses_for_job_ids(
    job_ids: list[str], machine_name: Optional[str]
) -> dict[str, str]:
    if not job_ids:
        return {}
    if machine_name is None:
        return _fetch_statuses_locally(job_ids)
    try:
        config = load_config()
    except EnvironmentError:
        return {}
    machine_config = config["machines"].get(machine_name) or config.get(machine_name)
    if machine_config is None:
        return {}
    return _fetch_statuses_remotely(job_ids, machine_name, machine_config)


def _fetch_time_left_locally(job_ids: list[str]) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    result = subprocess.run(
        ["squeue", "-h", "-j", query, "-o", "%i|%L"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return _parse_job_field_lines(result.stdout or result.stderr or "")


def _fetch_time_left_remotely(
    job_ids: list[str], machine_name: str, machine_config: dict
) -> dict[str, str]:
    if not job_ids:
        return {}
    query = ",".join(job_ids)
    try:
        hostname = ssh_host_from_config(machine_config, machine_name)
    except AttributeError:
        return {}
    remote_script = f"squeue -h -j {shlex.quote(query)} -o '%i|%L' 2>/dev/null || true"
    result = subprocess.run(
        ["ssh", *shlex.split(hostname), f"bash -lc {shlex.quote(remote_script)}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    return _parse_job_field_lines(result.stdout or result.stderr or "")


def _fetch_time_left_for_job_ids(
    job_ids: list[str], machine_name: Optional[str]
) -> dict[str, str]:
    if not job_ids:
        return {}
    if machine_name is None:
        return _fetch_time_left_locally(job_ids)
    try:
        config = load_config()
    except EnvironmentError:
        return {}
    machine_config = config["machines"].get(machine_name) or config.get(machine_name)
    if machine_config is None:
        return {}
    return _fetch_time_left_remotely(job_ids, machine_name, machine_config)


def job_status_text(job: dict) -> str:
    job_id = job.get("id")
    if job_id is None:
        return "not_submitted"
    statuses = _fetch_statuses_for_job_ids([str(job_id)], job.get("machine"))
    return statuses.get(str(job_id), "UNKNOWN")


def job_status_texts(jobs: list[dict]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in jobs:
        by_machine[job.get("machine")].append(job)

    for machine_name, machine_jobs in by_machine.items():
        job_ids = [str(job["id"]) for job in machine_jobs if job.get("id") is not None]
        machine_statuses = _fetch_statuses_for_job_ids(job_ids, machine_name)
        for job in machine_jobs:
            job_id = job.get("id")
            if job_id is None:
                statuses[job["name"]] = "not_submitted"
            else:
                statuses[job["name"]] = machine_statuses.get(str(job_id), "UNKNOWN")
    return statuses


def _job_remaining_times(jobs: list[dict], statuses: dict[str, str]) -> dict[str, str]:
    def _resolve_job_value(job_id: str, values: dict[str, str]) -> Optional[str]:
        exact = values.get(job_id)
        if exact is not None:
            return exact
        # Slurm can emit array/step-style identifiers (e.g., 12345_7 or 12345.batch).
        prefix_underscore = f"{job_id}_"
        prefix_dot = f"{job_id}."
        for key, value in values.items():
            if key.startswith(prefix_underscore) or key.startswith(prefix_dot):
                return value
        return None

    remaining: dict[str, str] = {job["name"]: "-" for job in jobs}
    by_machine: dict[Optional[str], list[dict]] = defaultdict(list)
    for job in jobs:
        by_machine[job.get("machine")].append(job)

    for machine_name, machine_jobs in by_machine.items():
        running = [
            job
            for job in machine_jobs
            if job.get("id") is not None and statuses.get(job["name"], "UNKNOWN").upper() == "RUNNING"
        ]
        if not running:
            continue
        job_ids = [str(job["id"]) for job in running]
        left = _fetch_time_left_for_job_ids(job_ids, machine_name)
        for job in running:
            resolved = _resolve_job_value(str(job["id"]), left)
            remaining[job["name"]] = resolved if resolved is not None else "UNKNOWN"
    return remaining


def _bundle_summary_lines(desired_date: Optional[datetime] = None) -> list[str]:
    summaries = latest_bundle_summaries(desired_date=desired_date)
    if not summaries:
        return ["No saved bundles found."]
    rows: list[dict[str, str]] = []
    for entry in summaries:
        bundle_name = entry["bundle"]
        saved_value = entry["date"].strftime("%Y-%m-%d %H:%M")

        try:
            jobs, _, _ = load_bundle(bundle_name, entry["date"])
        except (FileNotFoundError, OSError, ValueError, KeyError, json.JSONDecodeError):
            job_count = entry.get("job_count", 0)
            row = {
                "bundle": bundle_name,
                "saved": saved_value,
                "jobs": str(job_count),
                "submitted": "-",
                "running": "-",
                "completed": "-",
                "pending": "-",
                "failed": "-",
            }
            rows.append(row)
            continue

        statuses = job_status_texts(jobs)
        submitted = sum(1 for job in jobs if job.get("id") is not None)
        running = 0
        completed = 0
        pending = 0
        failed = 0
        for job in jobs:
            state = statuses.get(job["name"], "UNKNOWN").upper()
            if state == "COMPLETED":
                completed += 1
            elif state == "RUNNING":
                running += 1
            elif state in {"PENDING", "CONFIGURING"}:
                pending += 1
            elif state in FAILED_STATES:
                failed += 1

        row = {
            "bundle": bundle_name,
            "saved": saved_value,
            "jobs": str(len(jobs)),
            "submitted": str(submitted),
            "running": str(running),
            "completed": str(completed),
            "pending": str(pending),
            "failed": str(failed),
        }
        rows.append(row)

    headers = ["bundle", "saved", "jobs", "submitted", "running", "completed", "pending", "failed"]
    widths = {key: max(len(key), max(len(row[key]) for row in rows)) for key in headers}
    header = "  ".join(key.center(widths[key]) for key in headers)
    lines = [header]
    for row in rows:
        lines.append("  ".join(row[key].ljust(widths[key]) for key in headers))
    return lines


def bundle_index_context(desired_date: Optional[datetime] = None) -> str:
    return "\n".join(_bundle_summary_lines(desired_date=desired_date))


def bundle_jobs_context(bundle_name: str, desired_date: Optional[datetime] = None) -> str:
    def _requested_time(job: dict) -> str:
        slurm = job.get("slurm") or {}
        value = slurm.get("time")
        return str(value) if value else "-"

    def _requested_gpus(job: dict) -> str:
        slurm = job.get("slurm") or {}
        gres = slurm.get("gres")
        if not gres:
            return "0"
        text = str(gres)
        match = re.search(r"gpu(?::[^:,]+)?:(\d+)", text)
        if match:
            return match.group(1)
        if "gpu" in text.lower():
            return "1"
        return "0"

    def _dependencies_text(job: dict) -> str:
        deps = job.get("dependencies")
        if not deps:
            return "-"
        if isinstance(deps, (list, tuple)):
            return ",".join(str(dep) for dep in deps)
        return str(deps)

    jobs, _, bundle_date = load_bundle(bundle_name, desired_date)
    statuses = job_status_texts(jobs)
    remaining = _job_remaining_times(jobs, statuses)
    lines = [f"{bundle_name} {bundle_date.isoformat()}"]
    lines.append("Use --job <number|name> to inspect a job.")
    rows: list[tuple[str, str, str, str, str, str, str, str]] = []
    for index, job in enumerate(jobs, start=1):
        job_name = job["name"]
        status = statuses.get(job_name)
        if status is None:
            status = job_status_text(job)
        job_id = job.get("id")
        rows.append(
            (
                str(index),
                str(job_id) if job_id is not None else "-",
                job_name,
                _requested_time(job),
                _requested_gpus(job),
                _dependencies_text(job),
                remaining.get(job_name, "-"),
                status,
            )
        )

    idx_width = max(len("idx"), max(len(row[0]) for row in rows))
    id_width = max(len("id"), max(len(row[1]) for row in rows))
    name_width = max(len("name"), max(len(row[2]) for row in rows))
    time_width = max(len("time"), max(len(row[3]) for row in rows))
    gpus_width = max(len("gpus"), max(len(row[4]) for row in rows))
    deps_width = max(len("dependencies"), max(len(row[5]) for row in rows))
    remaining_width = max(len("remaining"), max(len(row[6]) for row in rows))
    status_width = max(len("status"), max(len(row[7]) for row in rows))
    lines.append(
        f"{'idx'.center(idx_width)}  "
        f"{'id'.center(id_width)}  "
        f"{'name'.center(name_width)}  "
        f"{'time'.center(time_width)}  "
        f"{'gpus'.center(gpus_width)}  "
        f"{'dependencies'.center(deps_width)}  "
        f"{'remaining'.center(remaining_width)}  "
        f"{'status'.center(status_width)}"
    )
    for index_text, job_id, job_name, time_text, gpus_text, deps_text, remaining_text, status in rows:
        deps_rendered = deps_text.center(deps_width) if deps_text == "-" else deps_text.ljust(deps_width)
        lines.append(
            f"{index_text.ljust(idx_width)}  "
            f"{job_id.ljust(id_width)}  "
            f"{job_name.ljust(name_width)}  "
            f"{time_text.ljust(time_width)}  "
            f"{gpus_text.ljust(gpus_width)}  "
            f"{deps_rendered}  "
            f"{remaining_text.ljust(remaining_width)}  "
            f"{status.ljust(status_width)}"
        )
    return "\n".join(lines)


def latest_bundle_status_context(desired_date: Optional[datetime] = None) -> str:
    summaries = latest_bundle_summaries(desired_date=desired_date)
    if not summaries:
        return "No saved bundles found."
    bundle_name = summaries[0]["bundle"]
    return bundle_jobs_context(bundle_name, desired_date)
