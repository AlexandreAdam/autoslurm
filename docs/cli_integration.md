# Typer CLI Guide

AutoSlurm works with any Python CLI because it reads the `--help` output to infer which arguments to store.
Typer builds on top of `click` and makes defining those arguments declarative, type-safe, and documented automatically, so we recommend it for every new script you plan to run through AutoSlurm.

## Install Typer

```bash
pip install typer
```

Full documentation is available at https://typer.tiangolo.com if you need autocomplete, callbacks, or advanced validators.

## Examples

### Run helper

```python
# src/my_project/train.py
def main(data_path: str, epochs: int, lr: float, seed: int):
    print(f"Training for {epochs} epochs at lr={lr} (seed={seed})")


if __name__ == "__main__":
    from typer import run

    run(main)
```

### Typer app with decorator

```python
from typer import Typer

app = Typer(help="Train a galaxy diffusion model.")


@app.command()
def train(dataset: str, epochs: int = 50, conditional: bool = False):
    print(f"{dataset=} {epochs=} {conditional=}")


if __name__ == "__main__":
    app()
```

Expose each command with its own entry point so AutoSlurm can schedule them individually.

## Scheduling with Typer arguments

```bash
autoslurm-schedule train-model \
    --bundle nightly-training \
    --time 06:00:00 --gres gpu:1 --cpus_per_task 8 --mem 48G \
    --data-path /shared/datasets/train.json \
    --epochs 40 --lr 5e-4 --seed 42
```

1. The CLI’s `--help` output tells AutoSlurm which options are available.
2. The job metadata lands in `$AUTOSLURM/jobs/nightly-training_*.json`.
3. When the job runs, the script receives the same Typer arguments you scheduled.
