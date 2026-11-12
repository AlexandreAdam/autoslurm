"""Retained pure validation of historical software-intent metadata.

These utilities neither deploy code nor select runtimes. New jobs use the
configured environment; software updates explicitly pull existing checkouts.
"""

import copy
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


_NAME = r"[A-Za-z0-9][A-Za-z0-9_.-]*"


def _name(value, field):
    if not isinstance(value, str) or not re.fullmatch(_NAME, value):
        raise ValueError(f"{field} must be a simple nonempty name.")
    return value


def _repository(value):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError("repository must be a credential-free HTTPS or SSH Git address.")
    address = urlsplit(value)
    if address.scheme in {"https", "ssh"}:
        valid = bool(address.hostname and address.path not in {"", "/"})
        valid = valid and not address.query and not address.fragment and address.password is None
        if address.scheme == "https" and address.username is not None:
            valid = False
    else:
        valid = bool(re.fullmatch(r"(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9_./~-]+", value))
    if not valid:
        raise ValueError("repository must be a credential-free HTTPS or SSH Git address.")
    return value


def normalize_software_manifest(manifest):
    """Return a copied historical request, without interpreting deployment intent.

    Runtime names and revisions remain data; they do not select an environment.
    Explicit revisions are full commit IDs or branch/tag names (optionally with
    refs/heads/ or refs/tags/). Installation paths stay repository-relative.
    """
    if not isinstance(manifest, dict) or set(manifest) - {"version", "runtime", "projects"}:
        raise ValueError("software must contain only version, runtime and projects.")
    if type(manifest.get("version", 1)) is not int or manifest.get("version", 1) != 1:
        raise ValueError("Unsupported software manifest version; expected 1.")
    projects = manifest.get("projects")
    if not isinstance(projects, list) or not projects:
        raise ValueError("software projects must be a nonempty list.")
    result = {"version": 1, "runtime": _name(manifest.get("runtime", "default"), "runtime"), "projects": []}
    names = set()
    for project in projects:
        if not isinstance(project, dict) or set(project) - {"name", "repository", "revision", "subdirectory"}:
            raise ValueError("Each project must contain only name, repository, revision and subdirectory.")
        name = _name(project.get("name"), "project name")
        if name in names:
            raise ValueError("Software project names must be unique.")
        names.add(name)
        repository = _repository(project.get("repository"))
        revision = project.get("revision")
        if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", revision)
                                     or ".." in revision or "//" in revision or revision.endswith("/")):
            raise ValueError("revision must be a full commit ID or a literal branch/tag name.")
        subdirectory = project.get("subdirectory", ".")
        if (not isinstance(subdirectory, str) or not subdirectory or "\\" in subdirectory
                or any(ord(c) < 32 for c in subdirectory) or PurePosixPath(subdirectory).is_absolute()
                or ".." in PurePosixPath(subdirectory).parts):
            raise ValueError("subdirectory must be a repository-relative path without traversal.")
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
    requests = [normalize_software_manifest(job["software"]) if "software" in job else None for job in jobs]
    if not requests:
        return None
    if any(request != requests[0] for request in requests[1:]):
        raise ValueError("Every job in a bundle must declare the same software manifest.")
    return requests[0]


def attach_software_manifest(bundle, manifest):
    """Copy a job dictionary and attach one normalized request to every job."""
    request = normalize_software_manifest(manifest)
    if not isinstance(bundle, dict) or not bundle or any(not isinstance(job, dict) for job in bundle.values()):
        raise ValueError("bundle must be a nonempty dictionary of jobs.")
    result = copy.deepcopy(bundle)
    for job in result.values():
        job["software"] = copy.deepcopy(request)
    return result
