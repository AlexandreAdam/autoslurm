# AutoSlurm

`autoslurm` turns repetitive SLURM scripting into a repeatable workflow service.
You describe what python script to run alongside the resources it need and the toolkit writes, stores, and submits the job locally or over SSH. 
Autoslurm produces structured JSON files as traces of the jobs so humans, CI jobs, or autonomous agents can reason about past and future runs.

## Why AutoSlurm?

- **Consistent infrastructure** – user-specific paths, accounts, and SSH details are stored once in a configuration file, not in your scripts.
- **Bundling jobs** – every scheduled job is serialized with timestamps, dependencies, and CLI args for later inspection or reruns.
- **Handling dependencies automatically** – jobs reference each other by name; AutoSlurm resolves the dependency graph and automatically complete the Slurm `--dependency` flags using the parent's jobID.
- **Shell and Python API** – User or agents can schedule jobs via a CLI (`autoslurm-schedule`, `autoslurm-submit`, …) or a Python API (`schedule_job`, `submit_jobs`).

## How The Docs Are Organized

- **Getting Started** – installation, configuration, and CLI basics with examples.
- **Configuration Workflow** – interactive setup and SSH best practices for defining machines.
- **Registering a Script** – optional packaging + entry-point guidance for avoiding path issues.
- **Typer CLI Guide** – quick Typer patterns so AutoSlurm can discover your CLI arguments automatically.
- **Agent Guide** – a package map and automation patterns so LLM-powered agents can reason about the codebase.

```{tableofcontents}

```
