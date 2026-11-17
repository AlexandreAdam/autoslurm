"""One-shot file-operation commands; no addressing, retry or scheduler policy."""

import errno
import subprocess

from .errors import DiagnosticCause, DiagnosticError, _file_operation_failure


def run_file_command(command, *, operation, stage, context, effects, effect,
                     timeout=30, input=None):
    effects[effect] = 'unknown'
    try:
        result = subprocess.run(command, input=input, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as native:
        if isinstance(native, subprocess.TimeoutExpired):
            code = 'command_timeout'
        elif isinstance(native, UnicodeError):
            code = 'protocol_invalid'
        elif isinstance(native, (FileNotFoundError, PermissionError)) or native.errno in {
                errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.ENOEXEC}:
            code = 'command_unavailable'
            effects[effect] = 'not_started'
        else:
            code = 'transport_failed'
        raise DiagnosticError(_file_operation_failure(code, operation, stage, context, effects,
            DiagnosticCause.from_exception(native, detail='The file-operation command did not complete normally.'))) from native
    code = result.returncode
    if type(code) is not int or not -(2**63) <= code < 2**63:
        raise DiagnosticError(_file_operation_failure('protocol_invalid', operation, stage, context, effects,
            DiagnosticCause('FileCommandResponse', 'No valid process exit code was returned.')))
    if code:
        problem = 'transport_failed' if code == 255 else 'operation_interrupted' if code < 0 else 'command_failed'
        raise DiagnosticError(_file_operation_failure(problem, operation, stage, context, effects,
            DiagnosticCause('FileCommand', 'External command failed; raw output is omitted.', returncode=code)))
    effects[effect] = 'succeeded'
    try:
        valid = isinstance(result.stdout, str) and len(result.stdout.encode('utf-8')) <= 65536
    except UnicodeError as native:
        raise DiagnosticError(_file_operation_failure('protocol_invalid', operation, stage, context, effects,
            DiagnosticCause.from_exception(native, detail='File-operation output was not valid UTF-8.'))) from native
    if not valid:
        raise DiagnosticError(_file_operation_failure('protocol_invalid', operation, stage, context, effects,
            DiagnosticCause('FileCommandResponse', 'Output was not text or exceeded 64 KiB.')))
    return result.stdout
