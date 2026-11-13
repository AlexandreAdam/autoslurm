"""One typed declaration for the experimental CLI/bundle authoring proof.

No AutoSlurm import is needed to execute this scientific command.
"""

from typing import Annotated

import typer


app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


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


if __name__ == '__main__':
    app()
