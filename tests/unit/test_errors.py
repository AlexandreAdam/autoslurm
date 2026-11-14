"""The diagnostic core is usable without backends, I/O or effect inference."""

import builtins
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from autoslurm.errors import (Diagnostic, DiagnosticCause, DiagnosticError,
                             command_failure, diagnostic_catalog, invalid_argument, missing_resource)


def test_core_loads_standalone_with_only_standard_library_imports(monkeypatch):
    # Package __init__ still eagerly imports legacy services; load this leaf alone
    # to verify its own dependency boundary, not the future package-import refactor.
    source = Path(__file__).parents[2] / "src/autoslurm/errors.py"
    specification = importlib.util.spec_from_file_location("isolated_diagnostics", source)
    module = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, specification.name, module)
    real_import = builtins.__import__
    imported = []

    def standard_only(name, *args, **kwargs):
        assert not name.startswith(("autoslurm", "packaging", "typer"))
        imported.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", standard_only)
    specification.loader.exec_module(module)
    assert set(imported) <= {"dataclasses", "re", "types", "typing", "_io"}
    assert module.Diagnostic("outcome_unknown", "submit", "dispatch").effects == {}


def test_diagnostics_do_not_read_files_environments_or_execute_commands(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Diagnostic core attempted I/O")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    diagnostic = missing_resource(operation="update_software", stage="environment_preflight",
        resource="Configured environment Python", path="/envs/science/bin/python",
        context={"machine": "cluster", "field": "venv_path"},
        cause=DiagnosticCause.from_exception(FileNotFoundError(2, "No such file")),
        effects={"git_pull": "not_started", "editable_install": "not_started"})
    payload = json.loads(json.dumps(diagnostic.to_dict(), allow_nan=False))
    assert payload["context"]["path"] == "/envs/science/bin/python"
    assert payload["cause"]["errno"] == 2
    assert payload["effects"] == {"git_pull": "not_started", "editable_install": "not_started"}


def test_every_catalogue_code_has_a_complete_serializable_default_contract():
    catalogue = diagnostic_catalog()
    for code, definition in catalogue.items():
        diagnostic = Diagnostic(code, "inspect", "read")
        data = json.loads(json.dumps(diagnostic.to_dict(), allow_nan=False))
        assert data["version"] == 1
        assert data["category"] == definition["category"]
        assert data["summary"] and data["next_action"]
        assert data["effects"] == {}  # Catalogue cannot infer effects from cause.
    catalogue["outcome_unknown"]["summary"] = "mutated"
    assert Diagnostic("outcome_unknown", "submit", "dispatch").summary != "mutated"


def test_same_timeout_can_describe_different_effects_without_retry_advice():
    cause = DiagnosticCause("TimeoutExpired", "The response timed out.")
    before = Diagnostic("command_timeout", "submit", "preflight", cause=cause,
                        effects={"submission": "not_started"})
    after = Diagnostic("command_timeout", "submit", "dispatch", cause=cause,
                       effects={"submission": "unknown"}, context={"receipt_path": "/runs/receipt.json"})
    assert before.code == after.code
    assert before.effects != after.effects
    assert "before" in after.next_action and "Inspect" in after.next_action
    assert after.to_dict()["context"]["receipt_path"] == "/runs/receipt.json"


def test_context_and_effects_are_detached_immutable_and_enrichment_cannot_redirect():
    context, effects = {"machine": "producing"}, {"submit": "partial"}
    diagnostic = Diagnostic("outcome_unknown", "submit", "dispatch", context=context, effects=effects)
    context["machine"], effects["submit"] = "other", "succeeded"
    assert diagnostic.context["machine"] == "producing"
    assert diagnostic.effects["submit"] == "partial"
    with pytest.raises(TypeError):
        diagnostic.effects["submit"] = "succeeded"
    with pytest.raises(FrozenInstanceError):
        diagnostic.stage = "other"
    enriched = diagnostic.with_context(job="reduce", job_id="123")
    assert enriched.context["job_id"] == "123" and "job" not in diagnostic.context
    with pytest.raises(ValueError, match="conflicts"):
        enriched.with_context(machine="other")
    data = enriched.to_dict()
    data["effects"]["submit"] = "not_started"
    assert enriched.effects["submit"] == "partial"


def test_secondary_failure_does_not_overwrite_primary_effects_or_evidence():
    primary = Diagnostic("outcome_unknown", "submit", "dispatch",
        context={"receipt_path": "/run/r.json", "job_id": "123"}, effects={"submission": "partial"})
    secondary = Diagnostic("storage_failed", "submit", "save_receipt", effects={"receipt_write": "unknown"})
    result = primary.with_secondary(secondary)
    assert result.code == primary.code and result.effects == primary.effects
    assert result.context["job_id"] == "123"
    assert result.to_dict()["secondary"][0]["code"] == "storage_failed"
    with pytest.raises(ValueError, match="leaf"):
        primary.with_secondary(result)
    with pytest.raises(ValueError, match="four"):
        primary.with_secondary(*([secondary] * 5))


def test_safe_serialization_redacts_before_bounding_and_never_serializes_payload_objects():
    secret = "credential-" + "x" * 5000
    cause = DiagnosticCause("CalledProcessError", f"https://name:{secret}@host/repo token=hidden\n" + "é" * 5000,
                            returncode=1)
    diagnostic = Diagnostic("command_failed", "update", "install", cause=cause,
        context={"path": "s3://name:password@bucket/data", "project": "science\x1b[31m\nNext: pretend"})
    serialized = json.dumps(diagnostic.to_dict(), ensure_ascii=False)
    assert secret not in serialized and "hidden" not in serialized and "password@" not in serialized
    assert "[redacted]@host" in serialized and len(cause.detail.encode()) <= 4096
    assert "\x1b" not in serialized and "\nNext" not in diagnostic.context["project"]
    with pytest.raises(TypeError):
        Diagnostic("internal_error", "submit", "dispatch", context={"job": object()})
    with pytest.raises(ValueError):
        Diagnostic("internal_error", "submit", "dispatch", context={"password": "secret"})


@pytest.mark.parametrize("detail", [
    'password="two words"', "passwd='two words'", "api_key=private", "Authorization: BearerSecret",
    "Authorization: Bearer private", "--token private", '--password "two words"',
    "https://example.test/?access_token=private&safe=ok", "https://example.test/?X-Amz-Signature=private",
    "-----BEGIN RSA PRIVATE KEY-----\nprivate\n-----END RSA PRIVATE KEY-----",
])
def test_known_credential_forms_are_redacted(detail):
    payload = DiagnosticCause("RuntimeError", detail).to_dict()
    assert "two words" not in payload["detail"] and "private" not in payload["detail"].replace("private key", "")
    assert "BearerSecret" not in payload["detail"]


@pytest.mark.parametrize("changes,exception", [
    ({"code": "invented"}, ValueError), ({"operation": "x\nother"}, ValueError),
    ({"stage": ""}, ValueError), ({"effects": {"submit": "rejected"}}, ValueError),
    ({"summary": ""}, ValueError), ({"next_action": ""}, ValueError),
    ({"cause": {}}, TypeError), ({"context": {"job": ["one"]}}, TypeError),
    ({"context": {"task": 2**100}}, ValueError),
])
def test_malformed_facts_are_programming_errors(changes, exception):
    arguments = {"code": "outcome_unknown", "operation": "submit", "stage": "dispatch", **changes}
    with pytest.raises(exception):
        Diagnostic(**arguments)


def test_named_constructors_require_observed_facts_without_reclassifying_transport():
    validation = invalid_argument(operation="plan", stage="validate", field="workers", explanation="workers must be positive.")
    assert validation.context["field"] == "workers" and validation.effects == {}
    failure = command_failure(operation="update", stage="install", command="pip",
        cause=DiagnosticCause("CalledProcessError", "Build failed", returncode=1),
        effects={"git_pull": "succeeded", "editable_install": "partial"})
    assert failure.code == "command_failed" and failure.effects["git_pull"] == "succeeded"
    with pytest.raises(ValueError):
        command_failure(operation="submit", stage="dispatch", command="ssh",
                        cause=DiagnosticCause("TimeoutExpired"), effects={"submit": "unknown"})
    with pytest.raises(ValueError, match="Conflicting"):
        missing_resource(operation="inspect", stage="read", resource="log", path="/new", context={"path": "/old"})


def test_legacy_exceptions_keep_message_payload_identity_and_optional_diagnostic_and_cause():
    from autoslurm import SoftwareUpdateError, SubmissionError
    receipt, evidence = {"jobs": {"one": {"id": "123"}}}, {"after_commit": "abc"}
    diagnostic = Diagnostic("outcome_unknown", "submit", "dispatch", effects={"submit": "unknown"})
    for constructor, payload, attribute in ((SubmissionError, receipt, "receipt"), (SoftwareUpdateError, evidence, "evidence")):
        legacy = constructor("unchanged message", payload)
        assert legacy.args == ("unchanged message",) and legacy.diagnostic is None
        assert isinstance(legacy, RuntimeError) and getattr(legacy, attribute) is payload
        assert constructor(None, payload).args == (None,)  # RuntimeError's original message contract.
        original = OSError("original cause")
        try:
            raise constructor("legacy message", payload, diagnostic=diagnostic) from original
        except DiagnosticError as error:
            assert error.__cause__ is original and error.diagnostic is diagnostic
            assert getattr(error, attribute) is payload
    assert str(DiagnosticError(diagnostic)) == diagnostic.summary
