"""Own one SSH master's local resources; no scheduler, transport fallback or keys."""

from dataclasses import dataclass, replace
import errno
import os
import shutil
import subprocess
import tempfile

from .errors import DiagnosticError, ConfigurationError, DiagnosticCause, _ssh_session_failure


@dataclass
class SessionCleanupIssue:
    stage: str
    error: BaseException


@dataclass
class OwnedSSHSession:
    directory: str
    options: list[str]
    destination: list[str]
    context: dict
    effects: dict

    @classmethod
    def create(cls, destination, context):
        # destination is already validated, pinned and contains no remote command.
        temporary_base = '/tmp' if os.name == 'posix' and os.path.isdir('/tmp') else None
        effects = {'session_directory': 'unknown', 'ssh_master_open': 'not_started',
                   'ssh_master_close': 'not_started', 'session_directory_cleanup': 'not_started'}
        try:
            directory = tempfile.mkdtemp(prefix='asl-ssh-', dir=temporary_base)
        except OSError as native:
            raise DiagnosticError(_ssh_session_failure('storage_failed', 'create_session_directory',
                {**context, 'path': temporary_base}, effects,
                DiagnosticCause.from_exception(native, detail='Local temporary directory creation failed.'))) from native
        effects['session_directory'] = 'succeeded'
        control_path = os.path.join(directory, 'cm-%C')
        options = ['-o', 'ControlMaster=auto', '-o', f'ControlPath={control_path}', '-o', 'ControlPersist=600']
        return cls(directory, options, list(destination), {**context, 'path': control_path}, effects)

    def open(self):
        path = os.path.join(self.directory, 'cm-' + 'x' * 40 + '.' + 'x' * 16)
        if os.name == 'posix' and len(os.fsencode(path)) >= 100:
            raise ConfigurationError(_ssh_session_failure('configuration_invalid', 'validate_control_path',
                                                           self.context, self.effects))
        self._command('open_session', 'ssh_master_open', ['-MNf'], timeout=30)

    def _command(self, stage, effect, options, *, timeout):
        command = [self.destination[0], *self.options, *options, *self.destination[1:]]
        self.effects[effect] = 'unknown'
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as native:
            if isinstance(native, subprocess.TimeoutExpired):
                problem = 'command_timeout'
            elif isinstance(native, UnicodeError):
                problem = 'protocol_invalid'
            elif isinstance(native, (FileNotFoundError, PermissionError)) or native.errno in {
                    errno.ENOENT, errno.ENOTDIR, errno.EACCES, errno.ENOEXEC}:
                problem = 'command_unavailable'
                self.effects[effect] = 'not_started'
            else:
                problem = 'transport_failed'
            raise DiagnosticError(_ssh_session_failure(problem, stage, self.context, self.effects,
                DiagnosticCause.from_exception(native, detail='The owned SSH session command did not complete normally.'))) from native
        code = result.returncode
        if type(code) is not int or not -(2**63) <= code < 2**63:
            raise DiagnosticError(_ssh_session_failure('protocol_invalid', stage, self.context, self.effects,
                DiagnosticCause('SSHSessionResponse', 'No valid command exit code was returned.')))
        if code:
            # Even SSH255 on open can follow creation of a master. Close our own
            # exact socket once, without claiming either a scheduler outcome or
            # definite absence of a connection.
            problem = 'transport_failed' if code == 255 else 'operation_interrupted' if code < 0 else 'command_failed'
            raise DiagnosticError(_ssh_session_failure(problem, stage, self.context, self.effects,
                DiagnosticCause('SSHSessionCommand', 'SSH command failed; raw output is omitted.', returncode=code)))
        self.effects[effect] = 'succeeded'

    def cleanup(self):
        """Attempt both stages; the caller preserves primary errors/interrupts."""
        issues = []
        if self.effects['ssh_master_open'] != 'not_started':
            try:
                self._command('close_session', 'ssh_master_close', ['-O', 'exit'], timeout=10)
            except BaseException as error:
                issues.append(SessionCleanupIssue('close_session', error))
        self.effects['session_directory_cleanup'] = 'unknown'
        try:
            shutil.rmtree(self.directory)
        except OSError as native:
            error = DiagnosticError(_ssh_session_failure('storage_failed', 'remove_session_directory',
                self.context, self.effects, DiagnosticCause.from_exception(native, detail='Local socket directory removal failed.')))
            error.__cause__ = native
            issues.append(SessionCleanupIssue('remove_session_directory', error))
        except BaseException as error:
            issues.append(SessionCleanupIssue('remove_session_directory', error))
        else:
            self.effects['session_directory_cleanup'] = 'succeeded'
        return issues

    def finish(self, primary, issues):
        """Attach bounded facts without replacing original bugs or exceptions."""
        if isinstance(primary, DiagnosticError) and primary.diagnostic is not None and primary.diagnostic.operation == 'ssh_session':
            primary.diagnostic = replace(primary.diagnostic, effects=self.effects)
        diagnostics = []
        for issue in issues:
            error = issue.error
            if isinstance(error, DiagnosticError) and error.diagnostic is not None:
                diagnostic = error.diagnostic
                if diagnostic.operation == 'ssh_session':
                    diagnostic = error.diagnostic = replace(diagnostic, effects=self.effects)
            else:
                code = 'operation_interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'internal_error'
                diagnostic = _ssh_session_failure(code, issue.stage, self.context, self.effects,
                    DiagnosticCause('SessionCleanupError', 'Cleanup raised an interrupt or unexpected error; inspect the original exception.'))
            diagnostics.append(diagnostic)
        if not issues:
            return
        primary.session_cleanup_diagnostics = tuple(d.to_dict() for d in diagnostics[:4])
        primary.session_cleanup_errors = tuple(issue.error for issue in issues if issue.error is not primary)[:4]
        if isinstance(primary, DiagnosticError) and primary.diagnostic is not None:
            additional = []
            for issue, diagnostic in zip(issues, diagnostics):
                if issue.error is not primary:
                    additional.extend([replace(diagnostic, secondary=()), *diagnostic.secondary])
            primary.diagnostic = primary.diagnostic.with_secondary(*additional[:4 - len(primary.diagnostic.secondary)])
        note = getattr(primary, 'add_note', None)
        if callable(note):
            for diagnostic in diagnostics[:4]:
                note(diagnostic.summary)
