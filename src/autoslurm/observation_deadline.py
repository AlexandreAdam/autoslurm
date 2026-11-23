"""Context-local deadline shared by existing read-only command adapters."""
from contextlib import contextmanager
from contextvars import ContextVar
import subprocess
import time

_deadline = ContextVar('autoslurm_observation_deadline', default=None)


def remaining_timeout(default):
    end = _deadline.get()
    if end is None:
        return default
    remaining = end - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired('campaign observation deadline', 0)
    return min(default, remaining)


@contextmanager
def observation_deadline(seconds):
    end = time.monotonic() + seconds
    parent = _deadline.get()
    token = _deadline.set(min(parent, end) if parent is not None else end)
    try:
        yield
    finally:
        _deadline.reset(token)
