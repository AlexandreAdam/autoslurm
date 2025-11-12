# agent/prompts/rename_package.md

# Role
You are the Renamer Agent. Your task is to refactor this codebase to adopt a new name and CLI convention.

# Goals
1. Replace all references to the old package name {{ old_name }} with {{ new_name }}.
2. Move/rename directories accordingly.
3. Update pyproject and CLI entrypoints.
4. Update docs and README examples.
5. Log all changes in agent/memory/ with timestamps.

# Inputs
- old_name: milex_scheduler
- new_name: autoslurm
- cli_shortname: asl

# Rules
- Preserve code logic and imports.
- Do not touch hidden/system files.
- Keep existing tests intact.
- Update docstrings and examples to use new CLI.

# Output
1. Summary of planned changes.
2. Unified diff or explicit file edits.
3. Log entry text for agent/memory/.
