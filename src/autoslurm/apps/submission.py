"""Read-only receipt inspection for terminal and agent callers."""

import argparse
import json
import sys

from ..submission import load_submission, list_submissions, refresh_submission, SubmissionError
from ..errors import SelectionError, RecordWriteError
from .error_output import exit_with_error, render_diagnostic


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect submission receipts; no jobs are submitted.")
    parser.add_argument("receipt", nargs="?", help="Exact local receipt path; omit to list receipts.")
    parser.add_argument("--bundle", help="Filter the local receipt list by bundle name.")
    parser.add_argument("--refresh", action="store_true", help="Fetch the selected execution-side receipt; may contact its recorded machine.")
    parser.add_argument("--json", action="store_true", help="Return structured receipt evidence.")
    parser.add_argument("--debug", action="store_true", help="Show original receipt errors.")
    args = parser.parse_args(argv)
    if args.refresh and not args.receipt:
        parser.error("--refresh requires an exact receipt path.")
    try:
        data = (refresh_submission if args.refresh else load_submission)(args.receipt) if args.receipt else list_submissions(args.bundle)
    except (SelectionError, RecordWriteError) as error:
        exit_with_error(error, json_output=args.json, debug=args.debug)
    except SubmissionError as exc:
        if args.debug:
            raise
        if args.json:
            data = dict(exc.receipt)
            if exc.diagnostic is not None:
                data["diagnostic"] = exc.diagnostic.to_dict()
            print(json.dumps(data))
        elif exc.diagnostic is not None:
            print(render_diagnostic(exc.diagnostic), file=sys.stderr)
            print(f"Submission: {exc.receipt['state']}; receipt: {exc.receipt['receipt_path']}", file=sys.stderr)
            known = [f"{name}={job['id']}" for name, job in exc.receipt["jobs"].items() if job.get("id")]
            if known:
                print("Known scheduler IDs: " + ", ".join(known), file=sys.stderr)
        else:
            print(str(exc))
        raise SystemExit(1) from exc
    if args.json:
        print(json.dumps(data, indent=2))
        return
    for receipt in data if isinstance(data, list) else [data]:
        print(f"{receipt['bundle']} {receipt['submission_id']} submission={receipt['state']}")
        for name, job in receipt["jobs"].items():
            print(f"  {name}: {job['state']}" + (f" id={job['id']}" if job.get("id") else "") + (f" ({job['error']})" if job.get("error") else ""))
        print(f"  receipt: {receipt['receipt_path']}")
