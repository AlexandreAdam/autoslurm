"""Standalone metadata-only worker, also sent verbatim to remote python3."""

import errno
import json
import os
import stat


def probe_path(path, *, raise_errors=False):
    """Follow symlinks; absence is different from inability to stat the path."""
    try:
        mode = os.stat(path).st_mode
    except OSError as error:
        if raise_errors:
            raise
        missing = error.errno in {errno.ENOENT, errno.ENOTDIR}
        return {'version': 1, 'path': path, 'state': 'missing' if missing else 'unavailable',
                'kind': None, 'errno': error.errno}
    return {'version': 1, 'path': path, 'state': 'exists',
            'kind': 'directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'other',
            'errno': None}


def probe_paths(paths):
    return {'version': 1, 'paths': [probe_path(path) for path in paths]}
