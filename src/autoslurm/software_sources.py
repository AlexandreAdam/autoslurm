"""Explicit source preparation on the current host, separate from runtime readiness."""

from pathlib import Path
from uuid import uuid4

from .git_projects import GitCommands, GitProjectError, managed_path, materialize_project
from .record_files import atomic_json
from .software_manifest import normalize_software_manifest


class SoftwarePreparationError(RuntimeError):
    """Failed source preparation, with exact partial evidence for the caller."""

    def __init__(self, message, evidence):
        self.evidence = evidence
        super().__init__(message)


def prepare_software_sources(manifest, *, software_root, git_commands=None):
    """Resolve Git requests and create isolated checkouts on this host.

    This host-side primitive does not SSH, install packages, select a machine,
    or submit jobs. Pass the preparation host's configured software_root. Every
    call creates a new source set and resolves omitted selectors upstream again.
    sources_prepared is deliberately distinct from a verified ready runtime.
    """
    request = normalize_software_manifest(manifest)
    root = Path(software_root)
    if not root.is_absolute():
        raise ValueError("software_root must be an absolute preparation-host path.")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    preparation_id = uuid4().hex
    directory = managed_path(root, "sources", preparation_id)
    directory.mkdir(parents=True, exist_ok=False)
    evidence_path = managed_path(root, "source_preparations", preparation_id + ".json")
    evidence = {"version": 1, "preparation_id": preparation_id, "state": "preparing_sources",
                "manifest": request, "software_root": str(root), "projects": [],
                "evidence_path": str(evidence_path)}
    record_created = False
    try:
        atomic_json(evidence_path, evidence, exclusive=True)
        record_created = True
        commands = git_commands if git_commands is not None else GitCommands()
        for project in request["projects"]:
            evidence["current_project"] = project["name"]
            evidence["projects"].append(materialize_project(project, root, directory / project["name"], commands))
            atomic_json(evidence_path, evidence)
        evidence.pop("current_project", None)
        evidence["state"] = "sources_prepared"
        atomic_json(evidence_path, evidence)
    except (Exception, KeyboardInterrupt) as error:
        stage = error.stage if isinstance(error, GitProjectError) else "preparation"
        message = str(error) if isinstance(error, GitProjectError) else "Source preparation failed or was interrupted."
        evidence.update(state="failed", error={"stage": stage, "message": message})
        if not record_created:
            # In particular, an exclusive-create collision must never replace
            # another operation's evidence with our failure record.
            evidence["tracking_error"] = "Source preparation evidence could not be saved."
        else:
            try:
                atomic_json(evidence_path, evidence)
            except (Exception, KeyboardInterrupt):
                evidence["tracking_error"] = "Source preparation evidence could not be saved."
        raise SoftwarePreparationError(message, evidence) from None
    return evidence
