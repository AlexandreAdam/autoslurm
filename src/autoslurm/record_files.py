"""Shared local JSON publication; no domain state or transport dependencies."""

import json
import os
from pathlib import Path
import tempfile

from .errors import (DiagnosticError, DiagnosticCause, RecordWriteError,
                     RecordCollisionError, record_write_failure)


def _write_error(error, path, stage, effects, *, problem="storage"):
    # Neither serializer messages nor arbitrary filesystem exception text are
    # safe record excerpts. Preserve native exceptions through normal chaining.
    cause = DiagnosticCause.from_exception(error, detail="Local JSON serialization failed." if problem == "serialization" else "Local filesystem operation failed.")
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
    """Publish complete JSON locally; exclusive creation never replaces a record.

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
        stage = "serialize"
        try:
            json.dump(data, stream, indent=indent)
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
