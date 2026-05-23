from __future__ import annotations

from autoslurm.apps import agent_context, configuration, experiment_context, initialize, schedule, submit


def test_leaf_apps_print_help_when_called_without_args(capsys):
    configuration.main([])
    schedule.main([])
    submit.main([])
    initialize.main([])
    experiment_context.main([])
    agent_context.main([])

    output = capsys.readouterr().out
    assert "usage:" in output
    assert "Schedule a job for a SLURM cluster" in output
    assert "Run scripts on a SLURM cluster" in output
    assert "Initialize a bundle of jobs" in output
    assert "Dump the context for a job or bundle" in output
    assert "Dump the agent documentation context" in output
