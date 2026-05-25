from __future__ import annotations

import json

from autoslurm.apps import bulk_submit_driver as app


def test_bulk_submit_driver_app_reads_payload_file_and_prints_json(
    tmp_path, monkeypatch, capsys
):
    payload = {
        "children_by_job": {"A": []},
        "slurm_names": {"A": "A.sh"},
        "slurm_dir": "/remote/slurm",
    }
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps(payload))

    class _Result:
        job_ids = {"A": "123"}
        levels = [["A"]]
        round_trips = 1

    monkeypatch.setattr(app, "submit_payload", lambda _payload: _Result())

    app.main(["--payload-file", str(payload_file)])
    output = json.loads(capsys.readouterr().out.strip())
    assert output["ok"] is True
    assert output["job_ids"] == {"A": "123"}
    assert output["levels"] == [["A"]]
    assert output["round_trips"] == 1


def test_bulk_submit_driver_app_reports_error(monkeypatch, capsys):
    monkeypatch.setattr(
        app.sys,
        "stdin",
        type(
            "Stdin",
            (),
            {
                "read": lambda self: json.dumps(
                    {
                        "children_by_job": {"A": []},
                        "slurm_names": {"A": "A.sh"},
                        "slurm_dir": "/remote/slurm",
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(app, "submit_payload", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")))

    try:
        app.main([])
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit(1)")

    output = json.loads(capsys.readouterr().out.strip())
    assert output["ok"] is False
    assert "boom" in output["error"]
