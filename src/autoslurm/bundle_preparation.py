"""In-memory preparation shared by preview and submission.

Preparation uses an already selected context. Filesystem/network preflight and
shell syntax checks are explicit operations after all definitions are prepared.
These internal values retain the existing dictionary contracts at the edges.
"""

import copy
from dataclasses import dataclass
from io import StringIO
import re

from .execution import ExecutionContext
from .job_to_slurm import write_slurm_content, validate_slurm_content
from .save_load_jobs import SNAPSHOT_KIND_KEY
from .submission import SUBMISSION_METADATA_KEY


@dataclass(frozen=True)
class PreparedJob:
    definition: dict
    execution: dict
    script: str

    @property
    def name(self):
        return self.definition["name"]


@dataclass(frozen=True)
class PreparedBundle:
    jobs: tuple[PreparedJob, ...]
    children_by_job: dict[str, list[str]]


def _validate_definition(job):
    if (job.get("id") is not None or job.get(SUBMISSION_METADATA_KEY)
            or job.get(SNAPSHOT_KIND_KEY) == "submission"):
        raise ValueError("Refusing to resubmit a submission snapshot; inspect its receipt and prepare a new definition explicitly.")
    if not isinstance(job.get("script"), str) or not job["script"].strip():
        raise ValueError("Every job needs a nonempty application command.")
    if not isinstance(job.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", job["name"]):
        raise ValueError("Job names must be simple names without path separators.")
    if not isinstance(job.get("slurm", {}), dict):
        raise ValueError("Job slurm options must be a mapping.")
    for field in ("script_args", "environment", "runtime_environment"):
        if job.get(field) is not None and not isinstance(job[field], dict):
            raise ValueError(f"{field} must be a mapping.")
    if job.get("slurm", {}).get("dependency") is not None:
        raise ValueError("Declare dependencies in the job graph, not Slurm options.")


def prepare_bundle(jobs, children_by_job, context: ExecutionContext) -> PreparedBundle:
    """Copy, validate and render loaded definitions; perform no external effects."""
    if not jobs:
        raise ValueError("Cannot submit an empty bundle.")
    definitions = copy.deepcopy(jobs)
    for definition in definitions:
        _validate_definition(definition)
        definition.setdefault("slurm", {})
    prepared = []
    for definition in definitions:
        execution = context.resolve_job(definition)
        output = StringIO()
        write_slurm_content(output, definition, context.config,
                            context=context, resolved=execution)
        prepared.append(PreparedJob(definition, execution, output.getvalue()))
    return PreparedBundle(tuple(prepared), copy.deepcopy(children_by_job))


def validate_prepared_bundle(bundle: PreparedBundle, context: ExecutionContext) -> None:
    """Check current input availability and shell syntax; never submit or write."""
    context.validate_resolved_jobs([job.execution for job in bundle.jobs])
    for job in bundle.jobs:
        validate_slurm_content(job.script)
