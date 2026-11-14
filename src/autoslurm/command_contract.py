"""Public in-memory named-option contracts; no parser or host dependencies.

Saved jobs remain ordinary dictionaries. Revalidation requires an explicit trusted
contract; loading a job never imports application code or discovers a parser.
"""

import copy
from dataclasses import asdict, dataclass
import math
import re
import shlex

from .argument_compilation import literal_argument

__all__ = ['CommandOption', 'CommandContract']


def _job_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
        raise ValueError('Job names must be simple nonempty names without path separators.')
    return value


def _names(values, label):
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) for value in values):
        raise ValueError(f'{label} must be a list or tuple of names.')
    if len(set(values)) != len(values):
        raise ValueError(f'{label} must not contain duplicate names.')
    return tuple(values)


@dataclass(frozen=True)
class CommandOption:
    name: str
    kind: str
    required: bool
    default: object = None
    minimum: int | float | None = None
    maximum: int | float | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', self.name):
            raise ValueError('Command option names must be ordinary named arguments.')
        if not isinstance(self.kind, str) or self.kind not in {'str', 'int', 'float', 'bool'} or type(self.required) is not bool:
            raise ValueError(f'Unsupported option contract for {self.name}.')
        for bound in (self.minimum, self.maximum):
            if bound is not None and (self.kind not in {'int', 'float'} or type(bound) not in (int, float) or not math.isfinite(bound)):
                raise ValueError(f'Invalid numeric bound for {self.name}.')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f'Invalid numeric range for {self.name}.')
        if self.kind == 'bool' and (self.required or self.default is not False):
            raise ValueError(f'{self.name}: only default-off boolean flags are supported.')
        if self.required and self.default is not None:
            raise ValueError(f'{self.name}: required options cannot have defaults.')
        if not self.required:
            self.validate(self.default)

    def validate(self, value):
        valid = type(value) is {'str': str, 'int': int, 'float': float, 'bool': bool}[self.kind]
        if self.kind == 'float' and type(value) is int:
            try:
                value, valid = float(value), True
            except OverflowError:
                valid = False
        if not valid:
            raise ValueError(f'{self.name}: expected {self.kind}, got {type(value).__name__}.')
        if self.kind == 'float' and not math.isfinite(value):
            raise ValueError(f'{self.name}: expected a finite number.')
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f'{self.name}: must be at least {self.minimum}.')
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f'{self.name}: must be at most {self.maximum}.')
        return value


@dataclass(frozen=True)
class CommandContract:
    """Validate scalar named settings and build ordinary saved-job dictionaries.

    ``validate`` fills current defaults for new settings. ``validate_job`` checks
    complete saved settings without silently adding defaults from a newer CLI.
    """
    script: str
    options: tuple[CommandOption, ...]
    input_args: tuple[str, ...] = ()
    path_args: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.script, str) or not self.script or any(ord(char) < 32 for char in self.script):
            raise ValueError('Provide a nonempty ordinary application command.')
        tokens = shlex.split(self.script)
        if not tokens or ' '.join(tokens) != self.script or any(shlex.quote(token) != token for token in tokens):
            raise ValueError('Command contracts require a literal command prefix with shell-safe words.')
        if not isinstance(self.options, (list, tuple)) or any(not isinstance(option, CommandOption) for option in self.options):
            raise ValueError('options must contain CommandOption values.')
        object.__setattr__(self, 'options', tuple(self.options))
        object.__setattr__(self, 'input_args', _names(self.input_args, 'input_args'))
        object.__setattr__(self, 'path_args', _names(self.path_args, 'path_args'))
        names = [option.name for option in self.options]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate command option names.')
        if not set(self.input_args + self.path_args) <= set(names):
            raise ValueError('Path declarations must name existing command options.')
        if set(self.input_args) & (set(self.path_args) | {'output_dir'}):
            raise ValueError('An argument cannot be both a required input and a result path.')
        for option in self.options:
            if option.name in self.input_args + self.path_args + ('output_dir',) and option.kind != 'str':
                raise ValueError(f'{option.name}: declared paths must be strings.')
            if not option.required:
                self._validate_value(option, option.default)

    def _validate_value(self, option, value):
        value = option.validate(value)
        literal_argument(value, name=option.name)
        if isinstance(value, str) and not value:
            raise ValueError(f'{option.name}: provide a nonempty value.')
        return value

    def validate(self, script_args):
        if not isinstance(script_args, dict):
            raise ValueError('script_args must be a named mapping.')
        names = {option.name for option in self.options}
        if set(script_args) - names:
            raise ValueError(f'Unknown command arguments: {sorted(map(str, set(script_args) - names))}.')
        values = {}
        for option in self.options:
            if option.required and option.name not in script_args:
                raise ValueError(f'{option.name}: required argument is missing.')
            values[option.name] = self._validate_value(option, script_args.get(option.name, option.default))
        return values

    def job(self, *, name, script_args, slurm=None, dependencies=()):
        """Build a new definition with all supported defaults made explicit."""
        values = self.validate(script_args)
        _job_name(name)
        if slurm is not None and not isinstance(slurm, dict):
            raise ValueError('slurm must be a mapping.')
        job = {'name': name, 'script': self.script, 'script_args': values, 'slurm': dict(slurm or {})}
        parents = _names(dependencies, 'dependencies')
        for parent in parents:
            if _job_name(parent) == name:
                raise ValueError('A job cannot depend on itself.')
        if parents:
            job['dependencies'] = list(parents)
        if self.input_args:
            job['input_args'] = list(self.input_args)
        if self.path_args:
            job['path_args'] = list(self.path_args)
        return job

    def validate_job(self, job):
        """Return a checked copy of an exact job using this trusted declaration.

        Check invocation/path identity and every saved setting. Do not fill
        missing defaults, change files, verify installed code or authorize retry.
        Extra job fields/record evidence are retained; graph/path readiness and
        submission-snapshot guards remain the normal engine's responsibility.
        """
        if not isinstance(job, dict):
            raise ValueError('A saved job must be a mapping.')
        _job_name(job.get('name'))
        if job.get('script') != self.script:
            raise ValueError('Saved job command does not match the supplied contract.')
        for field in ('input_args', 'path_args'):
            raw = job.get(field)
            declared = _names(() if raw is None else raw, field)
            if set(declared) != set(getattr(self, field)):
                raise ValueError(f'Saved job {field} does not match the supplied contract.')
        values = job.get('script_args')
        if not isinstance(values, dict):
            raise ValueError('Saved script_args must be a named mapping.')
        missing = {option.name for option in self.options} - set(values)
        if missing:
            raise ValueError(f'Saved job is missing explicit settings {sorted(missing)}; rebuild it explicitly against the current command.')
        validated = self.validate(values)
        if not isinstance(job.get('slurm', {}), dict):
            raise ValueError('Job slurm options must be a mapping.')
        # Reuse new-job checks for resources and dependency names, retaining all
        # other fields instead of manufacturing a new submission definition.
        self.job(name=job['name'], script_args=validated, slurm=job.get('slurm', {}),
                 dependencies=job.get('dependencies') if job.get('dependencies') is not None else ())
        checked = copy.deepcopy(job)
        checked['script_args'] = validated
        return checked

    def describe(self):
        """Plain discoverable metadata, deliberately not saved into a bundle."""
        return {'script': self.script, 'options': [asdict(option) for option in self.options],
                'input_args': list(self.input_args), 'path_args': list(self.path_args)}
