"""Retired untracked graph submission path; stable retains its pinned version."""

__all__ = []


def submit_jobs_legacy_remote(*args, **kwargs):
    raise RuntimeError("Legacy graph submission is retired; use submit_jobs with a receipt-capable prepared helper.")
