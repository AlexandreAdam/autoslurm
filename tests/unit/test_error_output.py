import io
import json

import pytest

from autoslurm.apps.error_output import exit_with_error, render_diagnostic
from autoslurm.errors import Diagnostic, DiagnosticCause, DiagnosticError


def diagnosis():
    return Diagnostic("outcome_unknown", "submit", "dispatch",
        context={"machine": "cluster", "receipt_path": "/runs/one.json", "job_id": "123"},
        cause=DiagnosticCause("TimeoutExpired", "Safe detail", returncode=-1),
        effects={"env": "succeeded", "analysis": "unknown"})


def test_text_and_json_present_same_diagnostic_on_the_correct_channel(capsys):
    diagnostic = diagnosis()
    for json_output in (False, True):
        with pytest.raises(SystemExit) as caught:
            exit_with_error(DiagnosticError(diagnostic), json_output=json_output)
        assert caught.value.code == 1 and caught.value.__suppress_context__
        captured = capsys.readouterr()
        if json_output:
            assert captured.err == ""
            payload = json.loads(captured.out)
            assert payload == {"status": "error", "message": diagnostic.summary, "diagnostic": diagnostic.to_dict()}
        else:
            assert captured.out == "" and captured.err == render_diagnostic(diagnostic) + "\n"
            for value in ("123", "/runs/one.json", "TimeoutExpired", "analysis=unknown", diagnostic.next_action):
                assert value in captured.err


@pytest.mark.parametrize("error,debug", [(ValueError("bug"), False), (DiagnosticError("legacy"), False),
    (KeyboardInterrupt(), False), (DiagnosticError(diagnosis()), True)])
def test_unexpected_legacy_interrupt_and_debug_errors_keep_original_exception(error, debug, capsys):
    original = OSError("inner")
    error.__cause__ = original
    with pytest.raises(type(error)) as caught:
        exit_with_error(error, debug=debug)
    assert caught.value is error and error.__cause__ is original
    assert capsys.readouterr() == ("", "")


def test_secondary_error_rendering_keeps_primary_unknown_outcome_and_custom_stream():
    diagnostic = diagnosis().with_secondary(Diagnostic("storage_failed", "submit", "save_receipt"))
    output = io.StringIO()
    with pytest.raises(SystemExit):
        exit_with_error(DiagnosticError(diagnostic), stream=output)
    assert "analysis=unknown" in output.getvalue()
    assert "Secondary:" in output.getvalue() and "storage_failed" in output.getvalue()
    assert output.getvalue().index("outcome_unknown") < output.getvalue().index("storage_failed")


def test_unknown_error_does_not_gain_expected_status_from_a_diagnostic_shaped_attribute():
    error = RuntimeError("unexpected")
    error.diagnostic = diagnosis()
    with pytest.raises(RuntimeError) as caught:
        exit_with_error(error, json_output=True)
    assert caught.value is error


def test_output_failure_preserves_initiating_error_and_original_cause():
    error = DiagnosticError(diagnosis())
    cause = OSError("original transport cause")
    error.__cause__ = cause
    output_error = BrokenPipeError("output pipe closed")

    class BrokenStream:
        def write(self, value):
            raise output_error

    with pytest.raises(DiagnosticError) as caught:
        exit_with_error(error, stream=BrokenStream())
    assert caught.value is error and error.__cause__ is cause
    assert error.__context__ is output_error
    assert error.diagnostic.context["job_id"] == "123"
