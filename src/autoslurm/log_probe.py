"""Standalone bounded regular-file reader, shared by local and SSH log reads."""

import base64
import os
import stat


def read_log(path, max_bytes):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 1048576:
        raise ValueError('Log reads require 1..1048576 bytes.')
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return {'state': 'error', 'kind': 'not_regular'}
        start = max(0, before.st_size - max_bytes)
        os.lseek(descriptor, start, os.SEEK_SET)
        data = os.read(descriptor, min(before.st_size, max_bytes))
        after = os.fstat(descriptor)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        changed = identity(before) != identity(after) or len(data) != min(before.st_size, max_bytes)
        try:
            changed = changed or identity(after) != identity(os.stat(path))
        except OSError:
            changed = True
        return {'state': 'ok_changed' if changed else 'ok', 'data': data, 'size': before.st_size}
    except FileNotFoundError:
        return {'state': 'missing'}
    except PermissionError:
        return {'state': 'error', 'kind': 'unreadable'}
    except OSError:
        return {'state': 'error', 'kind': 'read_failed'}
    finally:
        if descriptor is not None:
            os.close(descriptor)


def query_log_paths(paths, max_bytes):
    """Emit a bounded indexed response; no paths are discovered or scanned."""
    if not isinstance(paths, list) or not 1 <= len(paths) <= 300:
        raise ValueError('Select 1..300 explicit log candidate paths.')
    for index, path in enumerate(paths):
        result = read_log(path, max_bytes)
        if result['state'] in {'ok', 'ok_changed'}:
            print(f"{index}|{result['state']}|{result['size']}|{base64.b64encode(result['data']).decode()}")
        else:
            print(f"{index}|{result['state']}|{result.get('kind', '')}|")
