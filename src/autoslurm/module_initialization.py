"""Explicit, read-only discovery of a site's module initialization file."""

import shlex
import subprocess

from .config import is_remote_machine, normalize_machine_profile
from .errors import ConfigurationError, DiagnosticCause, _module_detection_failure
from .transport import ssh_command


MODULE_INITIALIZERS = (
    "/etc/profile.d/z00_lmod.sh",
    "/etc/profile.d/lmod.sh",
    "/etc/profile.d/modules.sh",
    "/usr/share/lmod/lmod/init/bash",
    "/usr/share/Modules/init/bash",
)


def detect_module_initializer(profile, machine=None):
    """Select the first readable known file; never source it or run env_command."""
    profile = normalize_machine_profile(profile, machine=machine)
    candidates = " ".join(shlex.quote(path) for path in MODULE_INITIALIZERS)
    probe = (f"for candidate in {candidates}; do\n"
             '    if test -f "$candidate" && test -r "$candidate"; then\n'
             '        printf \'%s\\n\' "$candidate"; exit 0\n'
             "    fi\ndone\nexit 1")
    remote = is_remote_machine(profile)
    command = (ssh_command(profile, machine, "bash -c " + shlex.quote(probe))
               if remote else ["bash", "-c", probe])
    context = {"field": "module_init"}
    if machine is not None:
        context["machine"] = machine
    if remote:
        context["ssh_alias"] = profile["ssh_alias"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as native:
        problem = "timeout" if isinstance(native, subprocess.TimeoutExpired) else "unavailable"
        raise ConfigurationError(_module_detection_failure(problem, context,
            DiagnosticCause.from_exception(native))) from native
    if result.returncode == 0 and result.stdout.rstrip("\n") in MODULE_INITIALIZERS:
        return result.stdout.rstrip("\n")
    # Raw SSH stderr may contain operator secrets or arbitrary startup output.
    cause = DiagnosticCause("ModuleDetectionResponse", "Read-only file detection did not return a selected initializer.",
                            returncode=result.returncode)
    problem = ("missing" if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()
               else "transport" if remote and result.returncode == 255
               else "response")
    raise ConfigurationError(_module_detection_failure(problem, context, cause))
