"""Pure literal argument compilation after machine-path resolution.

Each group is one displayed argument line containing one or more argv tokens.
Scalar options use --name=value, flags one token, and legacy raw lists several.
No shell expansion, parser discovery, path lookup or command execution occurs.
"""

from .errors import InvalidRequestError

import math
import re
import shlex


def literal_argument(value, *, name):
    """Validate a primitive value and return its literal command-line spelling."""
    if type(value) not in (str, int, float, bool):
        raise InvalidRequestError(f"{name}: arguments must be scalar str, int, float or bool values.", field='script_args', context={'option': name}, stage='compile_arguments')
    if type(value) is float and not math.isfinite(value):
        raise InvalidRequestError(f"{name}: argument must be a finite number.", field='script_args', context={'option': name}, stage='compile_arguments')
    text = str(value)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise InvalidRequestError(f"{name}: arguments must not contain control characters.", field='script_args', context={'option': name}, stage='compile_arguments')
    return text


def compile_script_arguments(script_args) -> tuple[tuple[str, ...], ...]:
    """Compile resolved values into ordered literal argv groups.

    Raw bundles retain None/False/empty-list omission, space-style lists and
    trailing __positionals__. Typed contracts intentionally support only scalars.
    """
    if not isinstance(script_args, dict):
        raise InvalidRequestError("script_args must be a named mapping.", field='script_args', stage='compile_arguments')
    groups = []
    flags = set()
    for name, value in script_args.items():
        if name == "__positionals__":
            continue
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise InvalidRequestError(f"Invalid script_args option name: {name!r}.", field='script_args', stage='compile_arguments')
        flag = "--" + name.replace("_", "-")
        if flag in flags:
            raise InvalidRequestError(f"Duplicate normalized script_args option: {flag}.", field='script_args', context={'option': name}, stage='compile_arguments')
        flags.add(flag)
        if value is None or value is False:
            continue
        if value is True:
            groups.append((flag,))
        elif isinstance(value, list):
            if value:
                groups.append((flag, *(literal_argument(item, name=f"{name}[{index}]")
                                       for index, item in enumerate(value))))
        else:
            groups.append((f"{flag}={literal_argument(value, name=name)}",))
    positionals = script_args.get("__positionals__", [])
    if not isinstance(positionals, list):
        raise InvalidRequestError("__positionals__ must be a list of scalar arguments.", field='__positionals__', stage='compile_arguments')
    groups.extend((literal_argument(value, name=f"__positionals__[{index}]"),)
                  for index, value in enumerate(positionals))
    return tuple(groups)


def render_script_arguments(groups) -> list[str]:
    """Shell-quote compiled literals, preserving readable --name=value lines."""
    lines = []
    for group in groups:
        if len(group) == 1 and re.match(r"--[A-Za-z0-9][A-Za-z0-9-]*=", group[0]):
            flag, value = group[0].split("=", 1)
            line = flag + "=" + shlex.quote(value)
        else:
            line = " ".join(shlex.quote(token) for token in group)
        lines.append("  " + line)
    return lines
