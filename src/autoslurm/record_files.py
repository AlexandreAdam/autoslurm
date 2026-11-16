"""Shared local record I/O; no domain state or transport dependencies."""

import json
import os
from pathlib import Path
import tempfile
import stat

from .errors import (DiagnosticError, DiagnosticCause, SelectionError, RecordWriteError,
                     RecordCollisionError, record_write_failure, _record_read_failure)


def _write_error(error, path, stage, effects, *, problem="storage"):
    # Neither serializer messages nor arbitrary filesystem exception text are
    # safe record excerpts. Preserve native exceptions through normal chaining.
    detail = ("Local text encoding failed." if stage == "write_text" else "Local JSON serialization failed.") if problem == "serialization" else "Local filesystem operation failed."
    cause = DiagnosticCause.from_exception(error, detail=detail)
    diagnostic = record_write_failure(stage=stage, path=str(path), effects=effects,
                                      cause=cause, problem=problem)
    return (RecordCollisionError if problem == "collision" else RecordWriteError)(diagnostic)


def _retain_cleanup(primary, cleanup):
    """Keep the initiating failure, including an interrupt or programming bug."""
    diagnosed = isinstance(cleanup, DiagnosticError) and cleanup.diagnostic is not None
    if isinstance(primary, DiagnosticError) and primary.diagnostic is not None and diagnosed:
        if len(primary.diagnostic.secondary) < 4:
            primary.diagnostic = primary.diagnostic.with_secondary(cleanup.diagnostic)
    else:
        note = getattr(primary, "add_note", None)
        if callable(note):
            note(cleanup.diagnostic.summary if diagnosed else "An unexpected failure also occurred during record cleanup.")
    # Native debug evidence stays outside serialized diagnostic facts.
    previous = getattr(primary, "record_cleanup_errors", ())
    primary.record_cleanup_errors = (*previous, cleanup)


def atomic_json(path, data, *, exclusive=False, indent=2):
    """Publish complete JSON with explicit publication/durability/cleanup facts."""
    return _atomic_record(path, lambda stream: json.dump(data, stream, indent=indent), exclusive=exclusive)


def atomic_text(path, content):
    """Publish a complete UTF-8 script through the same durability/cleanup owner."""
    return _atomic_record(path, lambda stream: stream.write(content), text=True)


def _atomic_record(path, write, *, exclusive=False, text=False):
    """Publish a complete record locally; exclusive creation never replaces it.

    Diagnostics distinguish publication not attempted, observed success and an
    unobserved outcome during link/replace. Directory durability is separate.
    Parent/temp files may exist even before destination publication starts.
    Cleanup never masks an initiating failure. No transaction, lock or retry.
    """
    path = Path(path)
    temporary = None
    stream = None
    directory = None
    primary = None
    effects = {"record_publication": "not_started", "record_durability": "not_started"}
    stage = "prepare_directory"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stage = "create_temporary"
        stream = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
        temporary = Path(stream.name)
        stage = "write_text" if text else "serialize"
        try:
            write(stream)
        except (TypeError, ValueError, UnicodeError) as error:
            raise _write_error(error, path, stage, effects, problem="serialization") from error
        stage = "sync_temporary"
        stream.flush()
        os.fsync(stream.fileno())
        stage = "close_temporary"
        stream.close()
        stream = None
        stage = "publish_record"
        effects.update(record_publication="unknown", record_durability="unknown")
        if exclusive:
            # Atomic no-clobber publication, with the temporary on the same filesystem.
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                effects.update(record_publication="not_started", record_durability="not_started")
                raise _write_error(error, path, stage, effects, problem="collision") from error
        else:
            os.replace(temporary, path)
        effects["record_publication"] = "succeeded"
        stage = "sync_directory"
        directory = os.open(path.parent, os.O_RDONLY)
        os.fsync(directory)
        effects["record_durability"] = "succeeded"
    except RecordWriteError as error:
        primary = error
        raise
    except OSError as error:
        primary = _write_error(error, path, stage, effects)
        raise primary from error
    except BaseException as error:
        # Evidence protection only: preserve bugs/interrupts, do not classify them.
        primary = error
        raise
    finally:
        cleanup_failure = None
        for cleanup_stage, cleanup in (
            ("close_temporary", stream.close if stream is not None and not stream.closed else None),
            ("close_directory", (lambda: os.close(directory)) if directory is not None else None),
            ("cleanup_temporary", temporary.unlink if temporary is not None else None),
        ):
            if cleanup is None:
                continue
            try:
                cleanup()
            except FileNotFoundError as error:
                if cleanup_stage == "cleanup_temporary":
                    continue  # Replacement already consumed the temporary file.
                cleanup_error = _write_error(error, path, cleanup_stage, effects)
                cleanup_error.__cause__ = error
            except OSError as error:
                cleanup_error = _write_error(error, path, cleanup_stage, effects)
                cleanup_error.__cause__ = error
            except BaseException as error:
                # Finish other cleanup, then propagate the original bug/interrupt
                # or retain it beside an already active primary failure.
                cleanup_error = error
            else:
                continue
            if primary is not None:
                _retain_cleanup(primary, cleanup_error)
            elif cleanup_failure is None:
                cleanup_failure = cleanup_error
            else:
                _retain_cleanup(cleanup_failure, cleanup_error)
        if primary is None and cleanup_failure is not None:
            raise cleanup_failure


def _read_error(path, *, code, stage="read_record", cause=None, context=None, summary=None):
    detail = None
    if isinstance(cause, json.JSONDecodeError):
        detail = f"Invalid JSON at line {cause.lineno}, column {cause.colno}."
    elif cause is not None:
        detail = "Local record read failed; expected regular UTF-8 JSON."
    return SelectionError(_record_read_failure(path=str(path), code=code, stage=stage,
        context=context, summary=summary,
        cause=DiagnosticCause.from_exception(cause, detail=detail) if cause is not None else None))


def _record_metadata(path, context):
    try:
        metadata = path.stat()
    except FileNotFoundError as error:
        try:
            path.lstat()
        except FileNotFoundError:
            code = "resource_missing"
        except OSError as observed:
            raise _read_error(path, code="resource_inaccessible", cause=observed, context=context) from observed
        else:
            code = "resource_inaccessible"
        raise _read_error(path, code=code, cause=error, context=context) from error
    except OSError as error:
        raise _read_error(path, code="resource_inaccessible", cause=error, context=context) from error
    if not stat.S_ISREG(metadata.st_mode):
        raise _read_error(path, code="resource_inaccessible", context=context,
                          summary="The selected record is not a regular file.")
    return metadata


def read_json(path, *, context=None):
    """Read regular UTF-8 JSON without blocking on a raced-in FIFO or hiding bugs.

    No directory creation or fallback. Domains validate the returned data. Close
    failures retain the primary parse/read error and its original native cause.
    """
    path = Path(path)
    _record_metadata(path, context)
    descriptor = stream = primary = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        stream = os.fdopen(descriptor, "r", encoding="utf-8")
        descriptor = None  # stream owns the descriptor after a successful fdopen
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise _read_error(path, code="resource_inaccessible", context=context,
                              summary="The selected record is not a regular file.")
        return json.load(stream)
    except FileNotFoundError as error:
        try:
            _record_metadata(path, context)
        except SelectionError as observed:
            code = observed.diagnostic.code
        else:
            code = "resource_inaccessible"
        primary = _read_error(path, code=code, cause=error, context=context)
        raise primary from error
    except (json.JSONDecodeError, UnicodeError) as error:
        primary = _read_error(path, code="record_invalid", cause=error, context=context)
        raise primary from error
    except OSError as error:
        primary = _read_error(path, code="resource_inaccessible", cause=error, context=context)
        raise primary from error
    except BaseException as error:
        primary = error  # Evidence protection only; no bug/interrupt classification.
        raise
    finally:
        try:
            if stream is not None:
                stream.close()
            elif descriptor is not None:
                os.close(descriptor)
        except BaseException as error:
            cleanup = (_read_error(path, code="resource_inaccessible", stage="close_record", cause=error, context=context)
                       if isinstance(error, OSError) else error)
            if cleanup is not error:
                cleanup.__cause__ = error
            if primary is None:
                raise cleanup
            _retain_cleanup(primary, cleanup)
