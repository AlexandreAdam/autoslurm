"""Pure generation of machine initialization, setup and activation in one shell."""

import shlex

from .errors import _environment_setup_failure_message


def activation_steps(profile):
    """Return labelled commands from an already validated machine profile."""
    steps = []
    initializer = profile.get("module_init")
    if initializer:
        path = shlex.quote(initializer)
        command = (
            "{\n"
            "if ! type module >/dev/null 2>&1; then\n"
            f"    test -f {path} && test -r {path} && source {path} && "
            "type module >/dev/null 2>&1\n"
            "fi\n"
            "}"
        )
        steps.append(("module_init", command))
    setup = profile.get("env_command")
    if isinstance(setup, str) and setup.strip():
        steps.append(("env_command", setup.strip()))
    venv = profile.get("venv_path")
    if isinstance(venv, str) and venv.strip():
        steps.append(("venv_path", f"source {shlex.quote(venv)}/bin/activate"))
    return steps


def render_environment_setup(steps):
    """Keep exports/functions in the job shell and guard each completed step."""
    lines = []
    for field, command in steps:
        message = shlex.quote(_environment_setup_failure_message(field))
        lines.append(command + "\n")
        lines.append(f'if [ "$?" -ne 0 ]; then printf \'%s\\n\' {message} >&2; exit 1; fi\n')
    return "".join(lines)
