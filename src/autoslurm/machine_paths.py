"""Pure normalization of infrastructure paths; no host or profile discovery."""

from pathlib import Path, PurePosixPath
import posixpath


def absolute_machine_path(value, label):
    """Normalize an infrastructure path without probing a local or remote host."""
    if not isinstance(value, (str, Path)) or not str(value).strip() or not PurePosixPath(str(value)).is_absolute():
        raise ValueError(f"{label} must be a nonempty absolute machine path.")
    if any(ord(character) < 32 for character in str(value)):
        raise ValueError(f"{label} must not contain control characters.")
    return posixpath.normpath(str(value))
