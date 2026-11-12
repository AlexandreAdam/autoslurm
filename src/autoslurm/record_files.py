"""Shared local JSON publication; no domain state or transport dependencies."""

import json
import os
from pathlib import Path
import tempfile


def atomic_json(path, data, *, exclusive=False, indent=2):
    """Publish complete JSON locally; exclusive creation never replaces a record.

    A failed write/serialization before publication leaves the destination intact.
    A directory-sync failure after publication can leave the complete record in
    place; this is not a multi-record transaction or a writer lock.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=indent)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Atomic no-clobber publication, with the temporary on the same filesystem.
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
