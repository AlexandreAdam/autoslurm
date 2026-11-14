"""Experimental, in-memory named-option contract; no parser or host dependencies.

MVP9 internal proof. Saved jobs remain ordinary dictionaries, without a persisted
contract or any promise of semantic revalidation after loading them.
"""

from dataclasses import asdict, dataclass
import math
import re
import shlex

from .argument_compilation import literal_argument


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
        if self.kind not in {'str', 'int', 'float', 'bool'} or type(self.required) is not bool:
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
    script: str
    options: tuple[CommandOption, ...]
    input_args: tuple[str, ...] = ()
    path_args: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.script, str) or not self.script or any(ord(char) < 32 for char in self.script):
            raise ValueError('Provide a nonempty ordinary application command.')
        tokens = shlex.split(self.script)
        if not tokens or ' '.join(tokens) != self.script or any(shlex.quote(token) != token for token in tokens):
            raise ValueError('This proof supports only a literal command prefix with shell-safe words.')
        names = [option.name for option in self.options]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate command option names.')
        if not set(self.input_args + self.path_args) <= set(names):
            raise ValueError('Path declarations must name existing command options.')
        for option in self.options:
            if option.name in self.input_args + self.path_args and option.kind != 'str':
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

    def job(self, *, name, script_args, slurm=None):
        values = self.validate(script_args)
        if not isinstance(name, str) or not name or '/' in name or '\\' in name:
            raise ValueError('Job name must be a nonempty simple name.')
        if slurm is not None and not isinstance(slurm, dict):
            raise ValueError('slurm must be a mapping.')
        job = {'name': name, 'script': self.script, 'script_args': values, 'slurm': dict(slurm or {})}
        if self.input_args:
            job['input_args'] = list(self.input_args)
        if self.path_args:
            job['path_args'] = list(self.path_args)
        return job

    def describe(self):
        """Plain discoverable metadata, deliberately not saved into a bundle."""
        return {'script': self.script, 'options': [asdict(option) for option in self.options],
                'input_args': list(self.input_args), 'path_args': list(self.path_args)}
