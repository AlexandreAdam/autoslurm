"""Bounded execution-receipt reads through the recorded transport only."""

import base64
from pathlib import Path
import subprocess

from .observation_deadline import remaining_timeout
from .errors import DiagnosticCause, DiagnosticError, _receipt_fetch_failure
from .transport import ssh_command

MAX_RECEIPT_BYTES = 1048576


def read_execution_receipt(receipt):
    """Fetch one whole small record using the shared standalone file reader."""
    context = {key: receipt[key] for key in ('machine', 'submission_id', 'receipt_path')}
    context.update(path=receipt['execution_receipt_path'], resource='execution_receipt')
    transport = receipt['execution'].get('transport')
    if not isinstance(transport, dict):
        raise DiagnosticError(_receipt_fetch_failure('identity', context))
    try:
        command = ssh_command(transport, receipt['machine'], 'python3 -B -')
    except (ValueError, AttributeError) as native:
        raise DiagnosticError(_receipt_fetch_failure('identity', context,
            DiagnosticCause(type(native).__name__, 'Recorded receipt transport is missing or invalid.'))) from native
    script = Path(__file__).with_name('log_probe.py').read_text()
    script += '\nquery_log_paths(' + repr([receipt['execution_receipt_path']]) + ', ' + str(MAX_RECEIPT_BYTES) + ')\n'
    try:
        result = subprocess.run(command, input=script, capture_output=True, text=True, timeout=remaining_timeout(30))
    except (OSError, subprocess.TimeoutExpired) as native:
        problem = 'timeout' if isinstance(native, subprocess.TimeoutExpired) else 'launch'
        raise DiagnosticError(_receipt_fetch_failure(problem, context,
            DiagnosticCause.from_exception(native))) from native
    if result.returncode != 0:
        problem = 'transport' if result.returncode == 255 else 'command'
        raise DiagnosticError(_receipt_fetch_failure(problem, context,
            DiagnosticCause('ReceiptReadProcess', 'Execution receipt reader did not complete.', returncode=result.returncode)))
    try:
        if len(result.stdout) > 4 * ((MAX_RECEIPT_BYTES + 2) // 3) + 128:
            raise ValueError('Receipt response exceeded its byte bound.')
        lines = result.stdout.splitlines()
        if len(lines) != 1:
            raise ValueError('Expected one indexed receipt response.')
        fields = lines[0].split('|')
        if len(fields) != 4 or fields[0] != '0':
            raise ValueError('Invalid indexed receipt response.')
        _, state, size, encoded = fields
        if state == 'missing' and not size and not encoded:
            problem = 'missing'
        elif state == 'error' and not encoded:
            problem = {'unreadable': 'unreadable', 'not_regular': 'not_regular', 'read_failed': 'read'}.get(size, 'protocol')
        elif state == 'ok_changed':
            problem = 'changed'
        elif state == 'ok':
            if not size.isdecimal() or int(size) > MAX_RECEIPT_BYTES:
                raise ValueError('Execution receipt exceeds the 1 MiB limit or has an invalid size.')
            data = base64.b64decode(encoded, validate=True)
            if len(data) != int(size) or len(data) > MAX_RECEIPT_BYTES:
                raise ValueError('Execution receipt was incomplete or exceeded its byte bound.')
            return data.decode('utf-8')
        else:
            problem = 'protocol'
    except (ValueError, UnicodeError) as native:
        raise DiagnosticError(_receipt_fetch_failure('protocol', context,
            DiagnosticCause(type(native).__name__, 'Execution receipt response was malformed, oversized or not UTF-8.'))) from native
    raise DiagnosticError(_receipt_fetch_failure(problem, context))
