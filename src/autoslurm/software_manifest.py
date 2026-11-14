"""Retained pure validation of historical software-intent metadata.

These utilities neither deploy code nor select runtimes. New jobs use the
configured environment; software updates explicitly pull existing checkouts.
"""

from .errors import InvalidRequestError, DiagnosticCause

import copy
from collections.abc import Iterable
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"


def _name(value, field):
    if not isinstance(value, str) or not re.fullmatch(_NAME, value):
        raise InvalidRequestError(f"{field} must be a simple nonempty name.", field=field, stage='validate_software')
    return value


def _repository(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        raise InvalidRequestError("repository must be a credential-free HTTPS or SSH Git address.", field='repository', stage='validate_software')
    try:
        address = urlsplit(value)
        hostname = address.hostname
    except ValueError as error:
        raise InvalidRequestError('repository must be a credential-free HTTPS or SSH Git address.',
            field='repository', stage='validate_software',
            cause=DiagnosticCause.from_exception(error, detail='The repository address could not be parsed.')) from error
    if address.scheme in {"https", "ssh"}:
        valid = bool(hostname and address.path not in {"", "/"})
        valid = valid and not address.query and not address.fragment and address.password is None
        if address.scheme == "https" and address.username is not None:
            valid = False
    else:
        valid = bool(re.fullmatch(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9_./~-]+", value))
    if not valid:
        raise InvalidRequestError("repository must be a credential-free HTTPS or SSH Git address.", field='repository', stage='validate_software')
    return value


def normalize_software_manifest(manifest):
    """Return a copied historical request, without interpreting deployment intent.

    Runtime names and revisions remain data; they do not select an environment.
    Explicit revisions are full commit IDs or branch/tag names (optionally with
    refs/heads/ or refs/tags/). Installation paths stay repository-relative.
    """
    if not isinstance(manifest, dict) or set(manifest) - {"version", "runtime", "projects"}:
        raise InvalidRequestError("software must contain only version, runtime and projects.", field='software', stage='validate_software')
    if type(manifest.get("version", 1)) is not int or manifest.get("version", 1) != 1:
        raise InvalidRequestError("Unsupported software manifest version; expected 1.", field='version', stage='validate_software')
    projects = manifest.get("projects")
    if not isinstance(projects, list) or not projects:
        raise InvalidRequestError("software projects must be a nonempty list.", field='projects', stage='validate_software')
    result = {"version": 1, "runtime": _name(manifest.get("runtime", "default"), "runtime"), "projects": []}
    names = set()
    for project in projects:
        if not isinstance(project, dict) or set(project) - {"name", "repository", "revision", "subdirectory"}:
            raise InvalidRequestError("Each project must contain only name, repository, revision and subdirectory.", field='projects', stage='validate_software')
        name = _name(project.get("name"), "project name")
        if name in names:
            raise InvalidRequestError("Software project names must be unique.", field='name', context={'project': name}, stage='validate_software')
        names.add(name)
        try:
            repository = _repository(project.get("repository"))
        except InvalidRequestError as error:
            error.diagnostic = error.diagnostic.with_context(project=name)
            raise
        revision = project.get("revision")
        if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", revision)
                                     or ".." in revision or "//" in revision or revision.endswith("/")):
            raise InvalidRequestError("revision must be a full commit ID or a literal branch/tag name.", field='revision', context={'project': name}, stage='validate_software')
        subdirectory = project.get("subdirectory", ".")
        if (not isinstance(subdirectory, str) or not subdirectory or "\\" in subdirectory
                or any(ord(c) < 32 for c in subdirectory) or PurePosixPath(subdirectory).is_absolute()
                or ".." in PurePosixPath(subdirectory).parts):
            raise InvalidRequestError("subdirectory must be a repository-relative path without traversal.", field='subdirectory', context={'project': name}, stage='validate_software')
        result["projects"].append({"name": name, "repository": repository, "revision": revision,
                                   "subdirectory": str(PurePosixPath(subdirectory))})
    # Project order is immaterial; canonical order makes shared requests comparable.
    result["projects"].sort(key=lambda project: project["name"])
    return result


def bundle_software_manifest(jobs):
    """Return one shared request, or None for an operator-prepared bundle.

    Existing bundle containers remain dictionaries of jobs. Every job opts into
    the same request, preventing a reducer from silently using different code.
    """
    if not isinstance(jobs, Iterable) or isinstance(jobs, (str, bytes, dict)):
        raise InvalidRequestError('Provide an iterable of job dictionaries.', field='jobs', stage='validate_software')
    requests = []
    for job in jobs:
        if not isinstance(job, dict):
            raise InvalidRequestError('Every job must be a dictionary.', field='job', stage='validate_software')
        try:
            requests.append(normalize_software_manifest(job['software']) if 'software' in job else None)
        except InvalidRequestError as error:
            if isinstance(job.get('name'), str):
                error.diagnostic = error.diagnostic.with_context(job=job['name'])
            raise
        if requests[-1] != requests[0]:
            raise InvalidRequestError('Every job in a bundle must declare the same software manifest.',
                field='software', stage='validate_software',
                context={'job': job.get('name') if isinstance(job.get('name'), str) else None})
    if not requests:
        return None
    return requests[0]


def attach_software_manifest(bundle, manifest):
    """Copy a job dictionary and attach one normalized request to every job."""
    request = normalize_software_manifest(manifest)
    if not isinstance(bundle, dict) or not bundle or any(not isinstance(job, dict) for job in bundle.values()):
        raise InvalidRequestError("bundle must be a nonempty dictionary of jobs.", field='bundle', stage='validate_software')
    result = copy.deepcopy(bundle)
    for job in result.values():
        job["software"] = copy.deepcopy(request)
    return result
