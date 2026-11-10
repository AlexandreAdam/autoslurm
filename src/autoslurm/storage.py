import os
from pathlib import Path

__all__ = [
    "storage_root",
    "jobs_dir",
    "slurm_dir",
    "out_dir",
    "config_file_path",
    "ensure_storage_dirs",
    "set_storage_root",
    "STORAGE_ROOT_ENVIRONMENT_VARIABLE",
]

STORAGE_ROOT_ENVIRONMENT_VARIABLE = "AUTOSLURM_STORAGE_ROOT"
_override_root: Path | None = None


def _absolute_root(path: str | Path) -> Path:
    if not str(path).strip():
        raise ValueError("AutoSlurm storage root must be a nonempty absolute path.")
    root = Path(path).expanduser()
    if not root.is_absolute():
        raise ValueError("AutoSlurm storage root must be an absolute path.")
    return root.resolve()


def set_storage_root(path: str | Path | None):
    """Override this process's root; None restores environment/default discovery."""
    global _override_root
    _override_root = None if path is None else _absolute_root(path)


def _root() -> Path:
    if _override_root is not None:
        return _override_root
    if STORAGE_ROOT_ENVIRONMENT_VARIABLE in os.environ:
        return _absolute_root(os.environ[STORAGE_ROOT_ENVIRONMENT_VARIABLE])
    return Path(__file__).resolve().parent.parent.parent


def storage_root() -> Path:
    return _root()


def jobs_dir() -> Path:
    return storage_root() / "jobs"


def slurm_dir() -> Path:
    return storage_root() / "slurm"


def out_dir() -> Path:
    return storage_root() / "out"


def config_file_path() -> Path:
    return storage_root() / "config.json"


def ensure_storage_dirs() -> None:
    for path in (jobs_dir(), slurm_dir(), out_dir()):
        path.mkdir(parents=True, exist_ok=True)
