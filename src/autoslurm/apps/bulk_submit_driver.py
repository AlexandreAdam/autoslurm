from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..bulk_submit_driver import BulkSubmitPayload, submit_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Internal AutoSlurm bulk submit driver entrypoint."
    )
    parser.add_argument(
        "--payload-file",
        type=Path,
        required=False,
        help="Path to JSON payload. If omitted, payload is read from stdin.",
    )
    return parser.parse_args(argv)


def _read_payload_text(payload_file: Path | None) -> str:
    if payload_file is not None:
        return payload_file.read_text()
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        payload_text = _read_payload_text(args.payload_file)
        payload_data = json.loads(payload_text)
        payload = BulkSubmitPayload(
            children_by_job=payload_data["children_by_job"],
            slurm_names=payload_data["slurm_names"],
            slurm_dir=payload_data["slurm_dir"],
        )
        result = submit_payload(payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "job_ids": result.job_ids,
                    "levels": result.levels,
                    "round_trips": result.round_trips,
                }
            )
        )
    except Exception as exc:  # pragma: no cover - exercised in tests
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)

