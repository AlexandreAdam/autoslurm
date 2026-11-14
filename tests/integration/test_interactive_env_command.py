"""Interactive setup edits flow through persistence, validation and job rendering."""

from io import StringIO
import json
import shlex
from subprocess import CompletedProcess

import pytest

from autoslurm import load_config, save_config
from autoslurm.apps import root
from autoslurm.execution import resolve_execution_context
from autoslurm.job_to_slurm import write_slurm_content
from autoslurm.storage import config_file_path


@pytest.mark.parametrize("initial,answer,expected", [
    (None, "module load jax/0.11.0", "module load jax/0.11.0"),
    ("module load old", "module load jax/0.11.0 && export DEVICE=gpu", "module load jax/0.11.0 && export DEVICE=gpu"),
    ("module load existing", "", "module load existing"),
    ("module load old", "-", None),
    (None, "", None),
])
def test_interactive_setup_edit_is_saved_validated_and_used_in_job(monkeypatch, initial, answer, expected):
    profile = {"ssh_alias": "cluster", "venv_path": "/env with spaces", "slurm_account": "account",
               "software_root": "/software", "results_root": "/data", "storage_root": "/state"}
    if initial is not None:
        profile["env_command"] = initial
    data = {"machines": {"remote": profile, "other": {"venv_path": "/other/env"}},
            "default_machine": "remote", "bundle_filter_mode": "all"}
    save_config(data)
    choices = iter(["1", "6"])
    prompts = []

    def respond(prompt):
        prompts.append(prompt)
        if prompt.startswith("Choice:"):
            return next(choices)
        if prompt.startswith("Select a number:"):
            return "1"
        if prompt.startswith("Environment setup command"):
            return answer
        return ""  # Keep every other setting, including remote/alias.

    commands = []

    def remote(command, **kwargs):
        assert command[:2] == ["ssh", "cluster"]
        commands.append(command)
        output = "/state\n" if "STORAGE_ROOT_ENVIRONMENT_VARIABLE" in command[-1] else ""
        return CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("builtins.input", respond)
    monkeypatch.setattr("subprocess.run", remote)
    root.main(["config", "--interactive"])
    if expected is None:
        profile.pop("env_command", None)
    else:
        profile["env_command"] = expected
    assert json.loads(config_file_path().read_text()) == data
    assert any(prompt.startswith("Environment setup command") for prompt in prompts)
    prefix = (expected + " && " if expected else "") + "source '/env with spaces'/bin/activate"
    # Validation still uses the saved setup and venv, without real SSH or execution.
    assert len(commands) == 3 and commands[0][-1] == "true"
    assert shlex.split(commands[1][-1])[2].startswith(prefix + " && python -c ")
    assert shlex.split(commands[2][-1])[2].startswith(prefix + " && env AUTOSLURM_STORAGE_ROOT=/state ")
    selected = load_config()["machines"]["remote"]
    context = resolve_execution_context("remote", selected, root_resolver=lambda *args: "/state")
    output = StringIO()
    write_slurm_content(output, {"name": "fit", "script": "science-fit", "slurm": {}}, selected, context=context)
    assert prefix + "\n" in output.getvalue()
    assert len(commands) == 3  # Rendering reuses context and does not validate/connect again.


def test_interactive_creation_can_set_setup_through_configuration_alias(monkeypatch):
    def respond(prompt):
        if prompt.startswith("Machine name"):
            return "science"
        if prompt.startswith("Python virtual environment path"):
            return "/env"
        if prompt.startswith("Environment setup command"):
            return "module load jax/0.11.0"
        return ""  # Local profile, optional fields unset.

    monkeypatch.setattr("builtins.input", respond)
    root.main(["configuration", "-i"])
    assert load_config()["machines"]["science"] == {
        "venv_path": "/env", "env_command": "module load jax/0.11.0"}
