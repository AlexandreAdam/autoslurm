# Resource Guidelines

Use these concise examples to steer scheduling prompts toward realistic resource requests.

## Light workloads (CPU-only, ~1h)

- **When to use:** small preprocessing tasks, quick evaluations, or tests that do not mention GPUs.
- **Sample SLURM flags:** `--time=01:00:00 --cpus_per_task=2 --mem=8G`
- **Why:** keeps queue time low while providing enough memory for small datasets.

## Heavy workloads (multi-hour/GPU)

- **When to use:** training, inference, or any work that explicitly mentions GPUs or long runtimes.
- **Sample flags:** `--time=12:00:00 --gres=gpu:1 --cpus_per_task=6 --mem=48G`
- **Guideline:** pair ~4–8 CPUs per GPU; scale memory by ~8 GB per extra GPU.

## Job arrays

- **When to use:** independent seeds, parameter sweeps, ensembles.
- **Sample flags:** `--array=1-5 --time=02:00:00 --cpus_per_task=2 --mem=12G`
- **Tip:** keep arrays modest (e.g., 5–20 elements). Break large sweeps into multiple bundles to avoid scheduler throttling.

## General principles

1. Ask for GPUs only when the user or context explicitly mentions them.
2. Keep walltimes tight: short tasks stay under an hour, heavy jobs stay within 12–24 hours unless justified.
3. Avoid over-requesting memory (match dataset/model size) and CPUs (use just enough for the described workload).
4. When providing guidance to an LLM, include the above examples so the model can repeat the exact flag string.
