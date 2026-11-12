"""Public inspection coordination: collect, project, cache, then attach artifacts."""

from datetime import datetime, timezone

from .inspection_artifacts import ArtifactRequest, attach_artifacts
from .inspection_cache import InspectionCache
from .inspection_collection import load_run, load_machine_profiles, collect_observations
from .inspection_state import resolve_jobs, project_run
from .bundle_selection import list_saved_bundles
from .storage import storage_root
from .submission import load_submission

__all__ = ["inspect_bundle", "inspect_bundles", "list_runs"]


def observe_job_statuses(jobs):
    """Explicit observation for status callers that already loaded definitions."""
    profiles, error = load_machine_profiles(jobs)
    observations = collect_observations(jobs, profiles)
    return resolve_jobs(jobs, observations, profiles=profiles, profile_error=error)


def _cached_view(run, profiles, profile_error, cache):
    view, error = cache.load_observation(run)
    if view is None:
        view = project_run(run, {}, profiles=profiles, profile_error=profile_error, fresh=False)
    else:
        view["freshness"] = "stale"
        view["errors"].extend(run.errors)
    if error:
        view["errors"].append(error)
    return view


def _fresh_view(run, observations, profiles, profile_error, cache):
    view = project_run(run, observations, profiles=profiles, profile_error=profile_error,
                       observed_at=datetime.now(timezone.utc).isoformat())
    if view["errors"]:
        previous, cache_error = cache.load_observation(run)
        if cache_error:
            view["errors"].append(cache_error)
        if previous:
            if previous["freshness"] == "failed" and previous.get("last_observed"):
                view["last_observed"] = previous["last_observed"]
            else:
                view["last_observed"] = {"observed_at": previous["observed_at"],
                                         "state": previous["state"], "freshness": "stale"}
    error = cache.save_observation(view)
    if error:
        view["errors"].append(error)
        if view["freshness"] == "fresh":
            view["freshness"] = "partial"
    return view


def inspect_bundles(bundle_paths, *, refresh=True, include_logs=False, job_name=None,
                    task_index=None, tail=40, max_log_bytes=65536, max_logs=20,
                    include_script=False, refresh_logs=None):
    runs = [load_run(path) for path in bundle_paths]
    request = ArtifactRequest(
        include_logs=include_logs, include_script=include_script, job_name=job_name,
        task_index=task_index, tail=tail, max_log_bytes=max_log_bytes, max_logs=max_logs,
        refresh_logs=refresh and refresh_logs is not False,
    )
    for run in runs:
        request.validate(run)
    jobs = [job for run in runs for job in run.jobs]
    profiles, profile_error = load_machine_profiles(jobs)
    observations = collect_observations(jobs, profiles) if refresh else {}
    root = storage_root()
    cache = InspectionCache(root)
    views = []
    for run in runs:
        view = (_fresh_view(run, observations, profiles, profile_error, cache) if refresh
                else _cached_view(run, profiles, profile_error, cache))
        views.append(attach_artifacts(view, run, request, profiles=profiles, root=root, cache=cache))
    return views


def inspect_bundle(bundle_path=None, *, receipt_path=None, **kwargs):
    if (bundle_path is None) == (receipt_path is None):
        raise ValueError("Select one exact bundle_path or receipt_path.")
    if receipt_path is not None:
        bundle_path = load_submission(receipt_path)["bundle_path"]
    return inspect_bundles([bundle_path], **kwargs)[0]


def list_runs(bundle_name=None):
    return [{"bundle": entry["bundle"], "bundle_path": str(entry["path"]), "saved_at": entry["date"].isoformat()}
            for entry in list_saved_bundles(bundle_name=bundle_name)]
