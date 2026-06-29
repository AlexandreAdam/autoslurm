from __future__ import annotations

from autoslurm import status


def test_combined_remote_fetch_uses_sacct_for_completed_jobs(monkeypatch):
    monkeypatch.setattr(
        status,
        "load_config",
        lambda: {"machines": {"remote": {"hostname": "remote.example.org"}}},
    )
    monkeypatch.setattr(
        status,
        "ssh_host_from_config",
        lambda machine_config, machine_name: "remote.example.org",
    )

    seen = {"ssh": 0}

    def fake_run(cmd, *args, **kwargs):
        assert cmd[0] == "ssh"
        seen["ssh"] += 1

        class Result:
            returncode = 0
            stdout = (
                "123|COMPLETED\n"
                "__AUTOSLURM_SPLIT__\n"
                "123|COMPLETED\n"
                "__AUTOSLURM_SPLIT__\n"
                "123|00:10:00\n"
            )
            stderr = ""

        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    statuses, time_left = status._fetch_statuses_and_time_left_for_job_ids(["123"], "remote")

    assert seen["ssh"] == 1
    assert statuses["123"] == "COMPLETED"
    assert time_left["123"] == "00:10:00"


def test_parse_status_lines_keeps_array_jobid_and_ignores_steps():
    parsed = status._parse_status_lines(
        "\n".join(
            [
                "123_0|COMPLETED",
                "123_0.batch|COMPLETED",
                "123_0.extern|COMPLETED",
                "123_1|FAILED",
                "123_1.batch|FAILED",
            ]
        )
    )

    assert parsed == {"123_0": "COMPLETED", "123_1": "FAILED"}
