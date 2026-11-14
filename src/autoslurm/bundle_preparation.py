"""In-memory preparation shared by preview and submission.

Preparation uses an already selected context. Filesystem/network preflight and
shell syntax checks are explicit operations after all definitions are prepared.
These internal values retain the existing dictionary contracts at the edges.
"""

from .errors import InvalidRequestError

import copy
from dataclasses import dataclass
from io import StringIO

from .execution import ExecutionContext
from .job_to_slurm import write_slurm_content, validate_slurm_content, _validate_render_definition
from .bundle_selection import SNAPSHOT_KIND_KEY
from .submission import SUBMISSION_METADATA_KEY
from .software_manifest import bundle_software_manifest


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
    _validate_render_definition(job, stage="prepare_bundle")
    if (job.get("id") is not None or job.get(SUBMISSION_METADATA_KEY)
            or job.get(SNAPSHOT_KIND_KEY) == "submission"):
        raise InvalidRequestError("Refusing to resubmit a submission snapshot; inspect its receipt and prepare a new definition explicitly.", field='submission', context={'job': job.get('name') if isinstance(job.get('name'), str) else None}, stage='prepare_bundle')
    if job.get("slurm", {}).get("dependency") is not None:
        raise InvalidRequestError("Declare dependencies in the job graph, not Slurm options.", field='slurm.dependency', context={'job': job['name']}, stage='prepare_bundle')


def prepare_bundle(jobs, children_by_job, context: ExecutionContext) -> PreparedBundle:
    """Copy, validate and render loaded definitions; perform no external effects."""
    if not isinstance(jobs, (list, tuple)) or not jobs:
        raise InvalidRequestError("Cannot submit an empty bundle.", field='bundle', stage='prepare_bundle')
    definitions = copy.deepcopy(jobs)
    for definition in definitions:
        try:
            _validate_definition(definition)
        except InvalidRequestError as error:
            error.diagnostic = error.diagnostic.with_context(machine=context.machine_name)
            raise
        definition.setdefault("slurm", {})
    if bundle_software_manifest(definitions) is not None:
        raise InvalidRequestError("Software manifests cannot select or prepare a runtime. Update the existing checkout explicitly and use the configured environment; runtime readiness is operator-managed.", field='software', stage='prepare_bundle')
    prepared = []
    for definition in definitions:
        output = StringIO()
        try:
            execution = context.resolve_job(definition)
            write_slurm_content(output, definition, context.config,
                                context=context, resolved=execution)
        except InvalidRequestError as error:
            error.diagnostic = error.diagnostic.with_context(job=definition['name'], machine=context.machine_name)
            raise
        prepared.append(PreparedJob(definition, execution, output.getvalue()))
    return PreparedBundle(tuple(prepared), copy.deepcopy(children_by_job))


def validate_prepared_bundle(bundle: PreparedBundle, context: ExecutionContext) -> None:
    """Check current input availability and shell syntax; never submit or write."""
    context.validate_resolved_jobs([job.execution for job in bundle.jobs])
    for job in bundle.jobs:
        try:
            validate_slurm_content(job.script)
        except InvalidRequestError as error:
            error.diagnostic = error.diagnostic.with_context(job=job.name, machine=context.machine_name)
            raise
