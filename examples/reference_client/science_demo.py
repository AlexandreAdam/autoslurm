"""A small scientific application with no AutoSlurm dependency."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path


def read_measurements(path):
    raw = Path(path).read_bytes()
    values = json.loads(raw)
    if not isinstance(values, list) or not values:
        raise ValueError("input must be a nonempty JSON list of numbers")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise ValueError("every measurement must be a finite number")
    return values, hashlib.sha256(raw).hexdigest()


def write_result(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compute a sum of squares, directly or in shards.")
    parser.add_argument("--mode", choices=("single", "shard", "reduce"), required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--parts-dir")
    parser.add_argument("--task-index", type=int)
    args = parser.parse_args(argv)
    try:
        values, digest = read_measurements(args.input_file)
        output = Path(args.output_dir)
        if args.mode == "shard":
            index = args.task_index
            if index is None:
                raw_index = os.environ.get("SLURM_ARRAY_TASK_ID")
                if raw_index is None:
                    raise ValueError("shard mode requires --task-index or SLURM_ARRAY_TASK_ID")
                index = int(raw_index)
            if not 0 <= index < len(values):
                raise ValueError("task index is outside the input measurements")
            result = {"index": index, "square": values[index] ** 2, "input_sha256": digest}
            write_result(output / f"part-{index}.json", result)
        else:
            if args.mode == "single":
                total = sum(value ** 2 for value in values)
            else:
                if args.parts_dir is None:
                    raise ValueError("reduce mode requires --parts-dir")
                total = 0
                for index, value in enumerate(values):
                    part = json.loads((Path(args.parts_dir) / f"part-{index}.json").read_text())
                    if (not isinstance(part, dict) or part.get("index") != index or part.get("input_sha256") != digest
                            or part.get("square") != value ** 2):
                        raise ValueError(f"part {index} does not match the current input")
                    total += part["square"]
            result = {"count": len(values), "sum_squares": total, "input_sha256": digest}
            write_result(output / "summary.json", result)
    except (OSError, ValueError, OverflowError) as exc:
        parser.exit(1, f"science-demo: {exc}\n")


if __name__ == "__main__":
    main()
