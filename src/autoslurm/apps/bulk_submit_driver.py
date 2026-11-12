from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..bulk_submit_driver import BulkSubmitPayload, submit_payload
from ..storage import slurm_dir
from ..submission import SUBMISSION_PROTOCOL, SubmissionError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Internal AutoSlurm bulk submit driver entrypoint."
    )
    parser.add_argument(
        "--capabilities", action="store_true", help="Report receipt protocol without submitting."
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
    if args.capabilities:
        print(json.dumps({"submission_protocol": SUBMISSION_PROTOCOL}))
        return
    try:
        payload_text = _read_payload_text(args.payload_file)
        payload_data = json.loads(payload_text)
        if Path(payload_data["slurm_dir"]) != slurm_dir():
            raise ValueError("Bulk payload script directory does not match the selected storage root.")
        if not payload_data.get("receipt"):
            raise ValueError("Submission receipt is required; untracked helper submission is retired.")
        payload = BulkSubmitPayload(
            children_by_job=payload_data["children_by_job"],
            slurm_names=payload_data["slurm_names"],
            slurm_dir=payload_data["slurm_dir"],
            receipt=payload_data.get("receipt"),
        )
        result = submit_payload(payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "job_ids": result.job_ids,
                    "levels": result.levels,
                    "round_trips": result.round_trips,
                    "receipt": getattr(result, "receipt", None),
                }
            )
        )
    except Exception as exc:  # pragma: no cover - exercised in tests
        print(json.dumps({"ok": False, "error": str(exc), "receipt": exc.receipt if isinstance(exc, SubmissionError) else None}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
