"""Read-only receipt inspection for terminal and agent callers."""

import argparse
import json

from ..submission import load_submission, list_submissions, refresh_submission, SubmissionError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect submission receipts; no jobs are submitted.")
    parser.add_argument("receipt", nargs="?", help="Exact local receipt path; omit to list receipts.")
    parser.add_argument("--bundle", help="Filter the local receipt list by bundle name.")
    parser.add_argument("--refresh", action="store_true", help="Fetch the selected execution-side receipt; may contact its recorded machine.")
    parser.add_argument("--json", action="store_true", help="Return structured receipt evidence.")
    args = parser.parse_args(argv)
    if args.refresh and not args.receipt:
        parser.error("--refresh requires an exact receipt path.")
    try:
        data = (refresh_submission if args.refresh else load_submission)(args.receipt) if args.receipt else list_submissions(args.bundle)
    except SubmissionError as exc:
        print(json.dumps(exc.receipt) if args.json else str(exc))
        raise SystemExit(1) from exc
    if args.json:
        print(json.dumps(data, indent=2))
        return
    for receipt in data if isinstance(data, list) else [data]:
        print(f"{receipt['bundle']} {receipt['submission_id']} submission={receipt['state']}")
        for name, job in receipt["jobs"].items():
            print(f"  {name}: {job['state']}" + (f" id={job['id']}" if job.get("id") else "") + (f" ({job['error']})" if job.get("error") else ""))
        print(f"  receipt: {receipt['receipt_path']}")
