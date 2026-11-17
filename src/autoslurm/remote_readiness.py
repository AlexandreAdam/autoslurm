"""Bounded readiness observations/parsing; no submission, setup policy or repair.

Transport owns addressing and launch command construction. This adapter owns
process facts and accepted responses; errors.py owns diagnosis and next steps.
"""

import errno
import json
from pathlib import PurePosixPath
import subprocess

from .errors import ConfigurationError, DiagnosticError, DiagnosticCause, _readiness_failure

MAX_READINESS_RESPONSE_BYTES = 65536
READINESS_TIMEOUT_SECONDS = 30


def readiness_context(profile, machine, *, field, executable=None, path=None):
    facts = {'field': field, 'resource': 'autoslurm_helper', 'command': 'ssh'}
    if machine is not None:
        facts['machine'] = machine
    if 'ssh_alias' in profile:
        facts['ssh_alias'] = profile['ssh_alias']
    if executable is not None:
        facts['executable'] = executable
    if path is not None:
        facts['path'] = path
    return facts


def configured_root(value, *, context):
    """Validate an explicit root before launching any command."""
    if (not isinstance(value, str) or not value.strip() or not PurePosixPath(value).is_absolute()
            or '..' in PurePosixPath(value).parts
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ConfigurationError(_readiness_failure('configuration_invalid', 'select_storage_root', context))
    return str(PurePosixPath(value))


def configured_python(profile, machine):
    value = profile.get('venv_path')
    context = readiness_context(profile, machine, field='venv_path')
    if (not isinstance(value, str) or not value.strip() or not PurePosixPath(value).is_absolute()
            or '..' in PurePosixPath(value).parts
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ConfigurationError(_readiness_failure('configuration_invalid', 'select_helper', context))
    return value.rstrip('/') + '/bin/python'


def run_readiness_probe(command, *, stage, context):
    """Run once; retain native causes and omit arbitrary SSH/startup output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=READINESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as native:
        if isinstance(native, subprocess.TimeoutExpired):
            code = 'command_timeout'
        elif isinstance(native, UnicodeError):
            code = 'protocol_invalid'
        elif isinstance(native, (FileNotFoundError, PermissionError)) or native.errno in {
                errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.ENOEXEC}:
            code = 'command_unavailable'
        else:
            code = 'transport_failed'
        cause = DiagnosticCause.from_exception(native, detail='The SSH readiness probe did not yield a valid response.')
        raise DiagnosticError(_readiness_failure(code, stage, context, cause)) from native
    code = result.returncode
    if type(code) is not int or not -(2**63) <= code < 2**63:
        raise DiagnosticError(_readiness_failure('protocol_invalid', stage, context,
            DiagnosticCause('ReadinessResponse', 'Probe returned no valid process exit code.')))
    if code:
        problem = 'transport_failed' if code == 255 else 'operation_interrupted' if code < 0 else 'command_failed'
        raise DiagnosticError(_readiness_failure(problem, stage, context,
            DiagnosticCause('ReadinessCommand', 'Remote command failed; raw SSH/startup output is omitted.', returncode=code)))
    try:
        valid = isinstance(result.stdout, str) and len(result.stdout.encode('utf-8')) <= MAX_READINESS_RESPONSE_BYTES
    except UnicodeError as native:
        raise DiagnosticError(_readiness_failure('protocol_invalid', stage, context,
            DiagnosticCause.from_exception(native, detail='Readiness output was not valid UTF-8 text.'))) from native
    if not valid:
        raise DiagnosticError(_readiness_failure('protocol_invalid', stage, context,
            DiagnosticCause('ReadinessResponse', 'Probe output was not text or exceeded 64 KiB.')))
    return result.stdout


def parse_storage_root(text, *, requested=None, context):
    root = text.strip()
    if (not root or not PurePosixPath(root).is_absolute() or '..' in PurePosixPath(root).parts
            or any(ord(char) < 32 or ord(char) == 127 for char in root)):
        raise DiagnosticError(_readiness_failure('protocol_invalid', 'read_storage_root', context,
            DiagnosticCause('StorageRootResponse', 'Expected one absolute path without traversal or control characters.')))
    if requested is not None and root != requested:
        raise DiagnosticError(_readiness_failure('compatibility_mismatch', 'read_storage_root',
            {**context, 'resolved_path': root}, DiagnosticCause('StorageRootResponse', 'Selected and reported storage roots differ.')))
    return root


def _unique_mapping(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Repeated capability key.')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Invalid JSON constant.')


def check_helper_capabilities(text, required, *, context):
    try:
        value = json.loads(text, object_pairs_hook=_unique_mapping, parse_constant=_invalid_constant)
        if not isinstance(value, dict):
            raise ValueError('Capabilities must be an object.')
    except (ValueError, RecursionError) as native:
        raise DiagnosticError(_readiness_failure('protocol_invalid', 'read_capabilities', context,
            DiagnosticCause.from_exception(native, detail='Expected one JSON capability object with unique keys.'))) from native
    if any(type(value.get(key)) is not int or value[key] != expected for key, expected in required.items()):
        raise DiagnosticError(_readiness_failure('compatibility_mismatch', 'check_capabilities', context,
            DiagnosticCause('HelperCapabilities', 'Required integer submission/tracking capabilities were not advertised.')))
