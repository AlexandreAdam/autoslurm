# Typer Integration Guide

Typer makes it easy to describe script arguments declaratively while giving you
type hints and automatic help pages. AutoSlurm can consume Typer apps with zero
custom glue provided the companion CLI prints the parsed arguments as JSON for
`autoslurm-schedule` to capture.

## Why pair Typer with AutoSlurm?

- **Single source of truth** – define arguments once and reuse them for both
  local development (`python -m my_app.train`) and scheduling.
- **Type safety** – Typer’s use of annotations mirrors the runtime signature you
  probably already call from Python code.
- **AutoSlurm compatibility** – Typer can serialize its parsed values to JSON,
  which is exactly what the scheduler expects from the `<script>-cli` companion.

## Project layout

```
my_project/
├─ src/my_app/train.py        # Main job logic
├─ src/my_app/cli.py          # Typer CLI that prints JSON
└─ pyproject.toml             # Exposes both entry points
```

In `pyproject.toml`:

```toml
[project.scripts]
train-model = "my_app.train:main"
train-model-cli = "my_app.cli:main"
```

- `train-model` is the executable AutoSlurm will run inside the SLURM script.
- `train-model-cli` is the Typer command that validates arguments and emits JSON
  describing them.

## Example: Typer CLI that emits JSON

```python
# src/my_app/cli.py
import json
from pathlib import Path
import typer

app = typer.Typer(help="Train the latest model with validated arguments.")

@app.command()
def main(
    data_path: Path = typer.Argument(..., help="Path to the prepared dataset."),
    epochs: int = typer.Option(10, min=1, help="Number of epochs to train."),
    lr: float = typer.Option(1e-3, help="Learning rate."),
    seed: int = typer.Option(0, help="Deterministic seed."),
):
    args = {
        "data_path": str(data_path),
        "epochs": epochs,
        "lr": lr,
        "seed": seed,
    }
    typer.echo(json.dumps(args))


if __name__ == "__main__":
    app()
```

When AutoSlurm runs `train-model-cli --epochs 20 --lr 5e-4`, this script prints
`{"epochs": 20, "lr": 0.0005, ...}` to stdout. The scheduler stores that JSON in
the bundle alongside SLURM parameters.

## Example: Job entry point

```python
# src/my_app/train.py
from pathlib import Path

def main(data_path: str, epochs: int, lr: float, seed: int):
    dataset = Path(data_path).read_text()  # Replace with real loading
    # Train the model using the provided hyperparameters...
    print(f"Training for {epochs} epochs at lr={lr} (seed={seed})")


if __name__ == "__main__":
    # Optional: allow `python -m my_app.train --data-path ...`
    from typer import run
    run(main)
```

AutoSlurm generates an `sbatch` script that ultimately executes
`train-model --data_path=... --epochs=...`.

## Scheduling with Typer arguments

```bash
autoslurm-schedule train-model \
    --bundle nightly-training \
    --time 06:00:00 --gres gpu:1 --cpus_per_task 8 --mem 48G \
    --data-path /shared/datasets/train.json \
    --epochs 40 --lr 5e-4 --seed 42
```

Steps performed:

1. `train-model-cli` validates the Typer arguments and prints JSON.
2. AutoSlurm records the job plus SLURM settings inside
   `$AUTOSLURM/jobs/nightly-training_*.json`.
3. When submitted, `train-model` receives the same arguments Typer parsed.

## Tips

- **Default values** – Typer defaults propagate automatically, so omit optional
  flags when scheduling if you want the CLI defaults.
- **Paths** – Convert `Path` objects to strings before serializing to JSON.
- **Multiple commands** – If your Typer app has multiple commands, expose each
  as a dedicated script/CLI pair so AutoSlurm can address them independently.
- **Validation errors** – A Typer `typer.BadParameter` exception will bubble up
  during `autoslurm-schedule`, preventing malformed jobs from being saved.

With this pattern, adding new job scripts is as simple as creating another pair
of entry points and letting Typer handle argument hygiene for you.
