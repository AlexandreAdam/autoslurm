"""Typed scientific commands shared by direct CLI and public bundle authoring.

No AutoSlurm import is needed to execute this scientific command.
"""

from typing import Annotated

import typer


app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
shard_app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
reduce_app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.command()
def single(
    input_file: Annotated[str, typer.Option()],
    output_dir: Annotated[str, typer.Option()],
    repeat: Annotated[int, typer.Option(min=1)] = 1,
    offset: float = 0.0,
    label: str = 'trial',
    include_values: bool = False,
):
    from pathlib import Path
    from science_demo import read_measurements, write_result

    values, digest = read_measurements(input_file)
    result = {'count': len(values) * repeat,
              'sum_squares': sum((value + offset) ** 2 for value in values) * repeat,
              'input_sha256': digest, 'label': label}
    if include_values:
        result['values'] = values
    write_result(Path(output_dir) / 'summary.json', result)


@shard_app.command()
def shard(input_file: Annotated[str, typer.Option()], output_dir: Annotated[str, typer.Option()]):
    """Compute the original array index supplied by Slurm."""
    from science_demo import main

    main(['--mode', 'shard', '--input-file', input_file, '--output-dir', output_dir])


@reduce_app.command()
def reduce(input_file: Annotated[str, typer.Option()], output_dir: Annotated[str, typer.Option()],
           parts_dir: Annotated[str, typer.Option()]):
    """Validate all expected shard outputs before publishing a summary."""
    from science_demo import main

    main(['--mode', 'reduce', '--input-file', input_file, '--output-dir', output_dir, '--parts-dir', parts_dir])


if __name__ == '__main__':
    app()
