from autoslurm.context import agent_context, agent_context_paths
from autoslurm.acp import execute_acp
import pytest


def test_agent_context_includes_key_docs():
    context = agent_context()
    assert "01_context_overview.md" in context
    assert "01_simple_job.sh" in context


def test_agent_context_paths_include_examples():
    paths = agent_context_paths()
    assert any("01_simple_job.sh" in str(path) for path in paths)


def test_agent_context_sections_filter():
    context = agent_context(sections=["09_task_inspect.md"])
    assert "Task: Inspect Experiments" in context
    assert "Task: Plan & Schedule Jobs" not in context


def test_agent_context_sections_keyword():
    context = agent_context(sections=["Schedule"])
    assert "Task: Plan & Schedule Jobs" in context
    assert "Task: Inspect Experiments" not in context


def test_schedule_context_contains_expected_sections():
    context = agent_context(sections=["10_task_schedule.md", "12_task_acp_reference.md"])
    assert "Task: Plan & Schedule Jobs" in context
    assert "ACP Reference" in context
    assert "Task: Inspect Experiments" not in context


def test_schedule_context_includes_resource_rules():
    context = agent_context(sections=["10_task_schedule.md", "06_resource_rules.md"])
    assert "Light workloads (CPU-only" in context
    assert "Heavy workloads (multi-hour/GPU)" in context


def test_schedule_context_keywords_only():
    context = agent_context(sections=["10_task_schedule", "acp_reference"])
    assert "Task: Plan & Schedule Jobs" in context
    assert "ACP Reference" in context
    assert "Task: Inspect Experiments" not in context


@pytest.mark.parametrize("task", ["schedule", "list_experiments", "inspect_experiments", "list_runs", "inspect_run"])
def test_task_context_delivers_current_client_contract(task):
    response = execute_acp({"action": "gather_context", "task": task})
    assert response["status"] == "success"
    context = response["result"]
    assert context.index("## 00_operating_rules.md") < context.index("## 01_client_workflow.md")
    assert "load_bundle_from_path(planned_path)" in context
    assert "Remote bulk-to-legacy" in context


def test_authoring_context_is_discoverable_by_task_and_explicit_section():
    response = execute_acp({'action': 'gather_context', 'task': 'integrate'})
    assert response['status'] == 'success'
    assert '## 14_typed_commands.md' in response['result']
    assert 'command.validate_job' in response['result']
    assert 'from autoslurm import CommandContract, CommandOption, from_typer' in response['result']
    selected = agent_context(sections=['14_typed_commands'])
    assert '## 14_typed_commands.md' in selected and 'Task: Inspect Experiments' not in selected


def test_packaged_authoring_context_does_not_need_a_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr('autoslurm.context.AGENT_FOLDER', tmp_path / 'missing-checkout-agent')
    selected = agent_context(sections=['14_typed_commands'])
    assert 'Typed command authoring' in selected and 'validate_job' in selected
