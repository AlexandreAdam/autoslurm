"""Pure, disposable explanations of supplied scheduler evidence.

Raw scheduler fields remain authoritative. Nothing here queries or persists.
"""

from collections import Counter

from .array_status import FAILED_STATES
from .execution import EXECUTION_METADATA_KEY, producing_machine


_REASONS = {
    "Dependency": ("dependency", "Waiting for dependencies", False),
    "DependencyNeverSatisfied": ("dependency_invalid", "Dependency cannot be satisfied", True),
    "Priority": ("priority", "Waiting for scheduling priority", False),
    "Resources": ("resources", "Waiting for resources", False),
    "JobArrayTaskLimit": ("array_limit", "Waiting for array concurrency limit", False),
    "JobHeldUser": ("hold", "Held by user", True),
    "JobHeldAdmin": ("hold", "Held by administrator", True),
    "BeginTime": ("begin_time", "Waiting for eligible start time", False),
    "InvalidAccount": ("configuration", "Check account", True),
    "AccountNotAllowed": ("configuration", "Account not allowed in partition", True),
    "InvalidQOS": ("configuration", "Check QOS", True),
    "QOSNotAllowed": ("configuration", "QOS not allowed", True),
    "PartitionDown": ("configuration", "Partition unavailable", True),
    "PartitionInactive": ("configuration", "Partition inactive", True),
    "BadConstraints": ("configuration", "Check requested constraints", True),
    "ReqNodeNotAvail": ("resources", "Requested nodes unavailable", False),
    "Reservation": ("reservation", "Waiting for reservation", False),
    "Licenses": ("resources", "Waiting for licenses", False),
}


def explain_state(state, reason=None, exit_code=None, *, freshness="fresh"):
    """Classify one observation; absent/unfamiliar reasons stay unknown."""
    code = reason.strip() if isinstance(reason, str) else ""
    if code.startswith("(") and code.endswith(")"):
        code = code[1:-1].strip()
    category, message, attention = "none", "", False
    if state == "PENDING":
        category, message, attention = _REASONS.get(code, ("unknown", "Pending; reason unavailable", False))
        if code.startswith(("Assoc", "QOS")) and code not in _REASONS:
            category, message = "policy_limit", f"Allocation/QOS policy: {code}"
        elif category == "unknown" and code not in {"", "None", "(null)", "Unknown"}:
            message = f"Pending: {code}"
    elif state in FAILED_STATES and state != "CANCELLED":
        category, message, attention = "failure", f"Failed: {code}" if code and code != "None" else state, True
        if exit_code and exit_code != "0:0":
            message += f" (exit={exit_code})"
    elif state == "UNKNOWN":
        category, message, attention = "unknown", "Status unavailable", True
    if freshness in {"stale", "never", "failed"} and message:
        message = "Last observed: " + message if freshness == "stale" else "Unverified: " + message
    return {"category": category, "message": message, "raw_reason": reason,
            "attention": attention, "freshness": freshness}


def _same_machine(left, right):
    if left.get("machine") != right.get("machine"):
        return False
    if EXECUTION_METADATA_KEY not in left and EXECUTION_METADATA_KEY not in right:
        return True
    try:
        return producing_machine(left, {})[0] == producing_machine(right, {})[0]
    except ValueError:
        return False


def _dependency_names(explanation, definition, definitions, by_name, *, freshness):
    if explanation["category"] != "dependency":
        return
    names = definition.get("dependencies") or []
    # Explicit Slurm expressions may use OR, afterany, external IDs, etc.
    # Do not reinterpret those as the bundle's ordinary afterok graph.
    if not names or (definition.get("slurm") or {}).get("dependency"):
        return
    dependencies = []
    for name in names:
        parent = by_name.get(name)
        parent_definition = definitions.get(name)
        verified = (freshness in {"fresh", "partial"} and parent and parent_definition
                    and _same_machine(definition, parent_definition)
                    and parent.get("id") and parent.get("observed_at") and not parent.get("errors"))
        complete = bool(verified and parent.get("state") == "COMPLETED" and parent["tasks"] and all(
            task.get("scheduler_state") == "COMPLETED" for task in parent["tasks"]))
        if not complete:
            dependencies.append({"name": name, "job_id": parent.get("id") if parent else None,
                "state": parent.get("state") if parent else "UNKNOWN", "verified": bool(verified)})
    explanation["dependencies"] = dependencies
    explanation["dependency_condition"] = "afterok"
    if dependencies:
        labels = [item["name"] + (" (unverified)" if not item["verified"] else
                  f" ({item['state'].lower()})" if item["state"] in FAILED_STATES else "")
                  for item in dependencies]
        prefix = ("Last observed: waiting for " if freshness == "stale" else
                  "Unverified: waiting for " if freshness in {"failed", "never"} else "Waiting for ")
        explanation["message"] = prefix + ", ".join(labels)
    elif freshness in {"fresh", "partial"}:
        explanation["message"] = "Dependency wait; parents observed completed"


def explain_jobs(definitions, jobs, *, freshness="fresh"):
    """Enrich provided job views in memory, preserving all original raw facts."""
    definitions = {job["name"]: job for job in definitions}
    by_name = {job["name"]: job for job in jobs}
    for job in jobs:
        own_freshness = freshness
        if job.get("errors") and freshness == "fresh":
            own_freshness = "partial"
        for item in [job, *job["tasks"]]:
            item["explanation"] = explain_state(item["state"], item.get("reason"),
                item.get("exit_code"), freshness=own_freshness)
            _dependency_names(item["explanation"], definitions[job["name"]], definitions,
                              by_name, freshness=own_freshness)
        if job["is_array"]:
            pending = Counter(task["explanation"]["category"] for task in job["tasks"] if task["state"] == "PENDING")
            job["explanation"]["pending_counts"] = dict(sorted(pending.items()))
            if pending:
                explanations = [task["explanation"] for task in job["tasks"] if task["state"] == "PENDING"]
                if len({item["message"] for item in explanations}) == 1:
                    job["explanation"] = {**explanations[0], "raw_reason": job.get("reason"), "pending_counts": dict(pending),
                        "message": f"{sum(pending.values())} pending: {explanations[0]['message']}"}
                else:
                    job["explanation"] = {"category": "mixed", "raw_reason": job.get("reason"),
                        "message": "; ".join(f"{count} {category}" for category, count in sorted(pending.items())),
                        "attention": any(item["attention"] for item in explanations),
                        "freshness": own_freshness, "pending_counts": dict(pending)}
            if job["counts"]["failed"]:
                job["explanation"].update(category="failure", attention=True,
                    message=f"{job['counts']['failed']} failed; " +
                    (job["explanation"]["message"] if pending else "inspect --array for task reasons"))
            message = job["explanation"]["message"]
            if message and own_freshness == "stale" and not message.startswith("Last observed:"):
                job["explanation"]["message"] = "Last observed: " + message
            elif message and own_freshness in {"never", "failed"} and not message.startswith("Unverified:"):
                job["explanation"]["message"] = "Unverified: " + message
    return jobs


def explain_view(view, definitions):
    """Apply after cache I/O so derived fields never change the cache format."""
    explain_jobs(definitions, view["jobs"], freshness=view["freshness"])
    previous = view.get("last_observed")
    if previous and previous.get("jobs"):
        explain_jobs(definitions, previous["jobs"], freshness="stale")
    return view
