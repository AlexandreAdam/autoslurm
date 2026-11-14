from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .definitions import DATE_FORMAT
from .context import agent_context
from .experiment_context import experiment_context
from .bundle_selection import list_saved_bundles
from .save_load_jobs import schedule_job
from .submission import load_submission, list_submissions, refresh_submission, SubmissionError
from .inspection import inspect_bundle, list_runs
from .errors import ConfigurationError, SelectionError

ACTION_FILE = Path(__file__).resolve().parent / "acp_action.json"


def _load_action_definitions() -> Dict[str, Dict[str, Any]]:
    try:
        with open(ACTION_FILE, "r") as f:
            actions = json.load(f)
    except Exception:  # pragma: no cover - config should be valid
        return {}
    return {action["name"]: action for action in actions}


ACTION_DEFINITIONS = _load_action_definitions()


__all__ = ["execute_acp", "list_bundles", "action_definitions"]


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, DATE_FORMAT)
        except ValueError:
            raise ValueError(
                f"Date '{value}' is not ISO-8601 or '{DATE_FORMAT}' formatted"
            )


def list_bundles(bundle_name: str, desired_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
    entries = []
    for entry in list_saved_bundles(desired_date=desired_date, bundle_name=bundle_name):
        entries.append(
            {
                "bundle": entry["bundle"],
                "date": entry["date"].isoformat(),
                "path": str(entry["path"]),
                "jobs": entry["jobs"],
                "state": entry['state'],
                "diagnostic": entry['diagnostic'],
            }
        )
    return entries


def _sections_for_task(task: str) -> List[str]:
    matches = []
    for action in ACTION_DEFINITIONS.values():
        keywords = action.get("keywords", [])
        sections = action.get("context_sections", [])
        if task == action["name"] or task in keywords:
            matches.extend(sections)
    return sorted(dict.fromkeys(matches))


def execute_acp(acl: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an Agent Communication Protocol request.

    The `acl` dict must include an `"action"` key (one of `inspect_experiments`,
    `list_experiments`, `schedule`, `gather_context`, `list_submissions`,
    `inspect_submission`, `list_runs`, `inspect_run`). Each action defines its
    own parameters. The return value is a
    dict with keys `status` and either `result` or `message`.
    """
    action = acl.get("action")
    if not action:
        return {"status": "error", "message": "Missing action"}

    try:
        if action == "list_submissions":
            return {"status": "success", "result": list_submissions(acl.get("bundle"))}
        if action == "list_runs":
            return {"status": "success", "result": list_runs(acl.get("bundle"))}
        if action == "inspect_run":
            return {"status": "success", "result": inspect_bundle(acl.get("bundle_path"), receipt_path=acl.get("receipt_path"),
                refresh=acl.get("refresh", True), include_logs=acl.get("include_logs", False),
                job_name=acl.get("job_name"), task_index=acl.get("task_index"), tail=acl.get("tail", 40),
                max_log_bytes=acl.get("max_log_bytes", 65536), max_logs=acl.get("max_logs", 20),
                stream=acl.get("stream", "both"))}
        if action == "inspect_submission":
            reader = refresh_submission if acl.get("refresh", False) else load_submission
            return {"status": "success", "result": reader(acl["receipt_path"])}
        if action == "inspect_experiments":
            bundle = acl["bundle"]
            date = _parse_date(acl.get("date"))
            payload = experiment_context(bundle, date)
            return {"status": "success", "result": payload}
        if action == "gather_context":
            selectors = acl.get("sections")
            task = acl.get("task")
            if not selectors and task:
                selectors = _sections_for_task(task)
            payload = agent_context(sections=selectors)
            return {"status": "success", "result": payload}
        if action == "list_experiments":
            bundle = acl["bundle"]
            result = list_bundles(bundle)
            return {"status": "success", "result": result}
        if action == "schedule":
            job = acl["job"]
            bundle = acl.get("bundle") or job.get("bundle")
            if bundle is None:
                raise ValueError("bundle must be specified when scheduling a job")
            append = bool(acl.get("append"))
            _, file_path = schedule_job(job, bundle_name=bundle, append=append)
            return {
                "status": "success",
                "result": {
                    "bundle": bundle,
                    "file": str(file_path),
                },
            }
        return {"status": "error", "message": f"Unknown action '{action}'"}
    except (SelectionError, ConfigurationError) as error:
        return {'status': 'error', 'message': str(error), 'diagnostic': error.diagnostic.to_dict()}
    except SubmissionError as exc:
        return {"status": "error", "message": str(exc), "result": exc.receipt}
    except Exception as exc:  # pragma: no cover - bubble up errors
        return {"status": "error", "message": str(exc)}


def action_definitions() -> Dict[str, Dict[str, Any]]:
    """Return the ACP action metadata."""
    return ACTION_DEFINITIONS
