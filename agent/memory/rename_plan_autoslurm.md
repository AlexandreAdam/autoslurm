# Rename Plan
Here is a concrete plan and a patch plan to refactor from milex_scheduler to autoslurm with CLI shortname asl. I include a high-level summary, explicit edits (as unified diffs / patch-like blocks), and a log entry for agent/memory/.

1) Summary of planned changes

- Package rename
  - Move/rename the core package from milex_scheduler to autoslurm.
  - Update all Python imports that reference milex_scheduler to autoslurm.
  - Preserve code logic and behavior; only package namespace changes.

- CLI and entry points
  - Change CLI entrypoint from the old name to asl.
  - Update pyproject.toml (or setup.cfg) to expose the new console script:
    - asl = autoslurm.cli:main (or equivalent entry depending on project layout)
  - Remove/retire the old milex entry if present.

- Project metadata
  - Update pyproject.toml [project] / [tool.poetry] name fields from milex_scheduler to autoslurm.
  - Ensure any internal version/project references reflect the new name.

- Documentation and README
  - Update all examples to use autoslurm and the asl CLI.
  - Replace command examples:
    - milex init / milex schedule … → asl init / asl schedule …
  - Update any internal references to the package name in docs (e.g., code samples, tutorials).

- Tests
  - Update tests to import autoslurm instead of milex_scheduler.
  - Ensure tests reference the new CLI alias asl where applicable.

- Docs strings and in-code references
  - Update docstrings, inline docs, and examples to reflect the new package name and CLI shortname.

- Logging
  - Add a log entry in agent/memory/ with a timestamp capturing the changes:
    - Rename of package
    - CLI shortname change
    - Pyproject changes
    - Docs/tests updates
    - CLI entrypoint changes

2) Explicit file edits (patch-like diffs)

Note: These blocks show the intended edits. The exact file paths may differ slightly in your repo; adjust to your actual structure if needed. The plan assumes a conventional layout where milex_scheduler is the top-level Python package and autoslurm is the new package name; a top-level autoslurm/ module contains cli.py and core.py, etc.

A) Rename package directory and adjust internal imports

diff --git a/milex_scheduler/__init__.py b/autoslurm/__init__.py
rename from: milex_scheduler/__init__.py
rename to:   autoslurm/__init__.py
- (contents preserved; package moved)

diff --git a/milex_scheduler/cli.py b/autoslurm/cli.py
rename from: milex_scheduler/cli.py
rename to:   autoslurm/cli.py
- (preserve contents; imports updated)

diff --git a/milex_scheduler/core.py b/autoslurm/core.py
rename from: milex_scheduler/core.py
rename to:   autoslurm/core.py
- (preserve contents)

diff --git a/milex_scheduler/submission.py b/autoslurm/submission.py
rename from: milex_scheduler/submission.py
rename to:   autoslurm/submission.py
- (preserve contents)

diff --git a/milex_scheduler/utils.py b/autoslurm/utils.py
rename from: milex_scheduler/utils.py
rename to:   autoslurm/utils.py
- (preserve contents)

Notes:
- If you have a package structure with nested folders, apply the same rename pattern for each module:
  - milex_scheduler/foo.py -> autoslurm/foo.py
  - milex_scheduler/foo/__init__.py -> autoslurm/foo/__init__.py
- After renaming, fix any relative imports within autoslurm to reflect the new package namespace if necessary (e.g., from .core import Scheduler remains correct; from milex_scheduler import … becomes from autoslurm import …).

B) Update CLI entry points and pyproject

diff --git a/pyproject.toml b/pyproject.toml
index 1234abcd..5678efgh 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,12 +1,12 @@
-[tool.poetry]
-name = "milex_scheduler"
+name = "autoslurm"
-version = "0.1.0"
-description = "Automated SLURM workflow scheduler"
+description = "Automated SLURM workflow scheduler"
-authors = ["Your Name <you@example.com>"]

-[tool.poetry.dependencies]
+[tool.poetry.dependencies]
 python = "^3.8"

@@ -20,7 +20,12 @@

-[tool.poetry.scripts]
-milex = "milex_scheduler.cli:main"
+[tool.poetry.scripts]
+asl = "autoslurm.cli:main"
+# Optional: keep a backwards-compat alias for a transition period
+# milex = "autoslurm.cli:main"  (if you want to support old CLI during a deprecation window)

-# If you previously had entry points or a console_scripts mapping, adjust accordingly
+# Ensure all existing entry points that referenced milex_scheduler are updated to autoslurm

Notes:
- The exact key names (name, description, dependencies) should match your current pyproject.toml structure. The crucial change is:
  - project name from milex_scheduler to autoslurm
  - console script from milex (or milex CLI) to asl
- If you use setup.cfg or setup.py, apply equivalent changes there as well.

C) Documentation and README edits

diff --git a/README.md b/README.md
index a1b2c3d4..d4c3b2a1 100644
--- a/README.md
+++ b/README.md
@@ -10,7 +10,7 @@
-Example:
-  milex init
+Example:
+  asl init
@@ -25,7 +25,7 @@
-Example:
-  milex schedule train_model.py --time 04:00:00 --gpus 1
+Example:
+  asl schedule train_model.py --time 04:00:00 --gpus 1
@@ -60,7 +60,7 @@
-Submitting with milex submit --remote
+Submitting with asl submit --remote

diff --git a/docs/usage.md b/docs/usage.md
index 9a8b7c6d..e7f8a9b 100644
--- a/docs/usage.md
+++ b/docs/usage.md
@@ -1,12 +1,12 @@
-CLI: milex
+CLI: asl
@@ -15,7 +15,7 @@
-mlx init
+asl init
@@ -30,7 +30,7 @@
-mlx submit --remote
+asl submit --remote

Notes:
- Replace all occurrences of milex_scheduler with autoslurm in code blocks.
- Replace CLI commands from milex or milex-cli style to asl style, and reflect the new package namespace autoslurm.

D) Tests

diff --git a/tests/test_cli.py b/tests/test_cli.py
index c0ffee0..deadbeef 100644
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,6 @@
-import milex_scheduler.cli as cli
+import autoslurm.cli as cli

-def test_main_help():
+def test_main_help():
     # simple smoke test for help flag
-    assert cli.main(["--help"]) & 0 == 0
+    assert cli.main(["--help"]) == 0

diff --git a/tests/test_imports.py b/tests/test_imports.py
index 1111111..2222222 100644
--- a/tests/test_imports.py
+++ b/tests/test_imports.py
@@ -1,5 +1,5 @@
-import milex_scheduler as ms
+import autoslurm as ms
 def test_import():
     # ensure module imports without error
-    assert hasattr(ms, "Scheduler")
+    assert hasattr(ms, "Scheduler")

Notes:
- Update all tests to import autoslurm instead of milex_scheduler.
- Ensure tests that reference CLI behavior use the asl alias where applicable.

E) CLI behavior and code references

diff --git a/autoslurm/cli.py b/autoslurm/cli.py
index aaaa1111..bbbb2222 100644
--- a/autoslurm/cli.py
+++ b/autoslurm/cli.py
@@ -1,12 +1,12 @@
-def main(args=None):
+def main(args=None):
-    # previous behavior referenced milex_scheduler
+    # updated to autoslurm namespace and asl CLI name
     ...
-    return 0
+    return 0
Notes:
- All internal imports within autoslurm/ should reference autoslurm.* (not milex_scheduler.*).
- The public entry point remains main(), but the console script alias should be asl (see pyproject changes).

F) Docsstrings and code examples

diff --git a/autoslurm/__init__.py b/autoslurm/__init__.py
index c0dec0c..d0e0f0e 100644
--- a/autoslurm/__init__.py
+++ b/autoslurm/__init__.py
@@ -1,3 +1,5 @@
+"""
+autoslurm: refactored namespace for the SLURM automation toolkit.
+"""
-from milex_scheduler.core import Scheduler
+from .core import Scheduler
 __all__ = ["Scheduler"]

Notes:
- Keep docstrings accurate; update references that mention milex_scheduler.

G) Documentation/help text about CLI name

diff --git a/docs/cli_help.md b/docs/cli_help.md
index 1a2b3c4d..4d3c2b1a 100644
--- a/docs/cli_help.md
+++ b/docs/cli_help.md
@@ -1,6 +1,6 @@
-Usage: milex [OPTIONS] COMMAND [ARGS]...
+Usage: asl [OPTIONS] COMMAND [ARGS]...
@@ -20,7 +20,7 @@
-Examples:
-  milex init
-  milex schedule ...
+Examples:
+  asl init
+  asl schedule ...

Notes:
- Ensure all docs reflect asl as the CLI alias and autoslurm as the package name.

3) Logging for agent/memory/ with a timestamp

Log entry text to log in agent/memory/ (e.g., as a new file with a timestamp in the filename, or appended to an existing log). Example content:

2025-11-12 14:30:01 UTC | INFO | Refactor: Rename package milex_scheduler to autoslurm and CLI shortname to asl.
- Updated package namespace: autoslurm
- Updated CLI entry point: asl = autoslurm.cli:main
- Updated pyproject.toml: project name -> autoslurm; scripts -> asl
- Updated imports across codebase: from milex_scheduler.* to autoslurm.*
- Updated README and docs examples to use asl and autoslurm
- Updated tests to import autoslurm
- Note: Tests logic unchanged; only namespaces and CLI name changed.
- Next steps: run test suite, update any remaining hard-coded references, verify packaging build, and ensure docs reflect new names.

4) Additional guidance and considerations

- If you have any hidden modules that import milex_scheduler directly, search and replace carefully for all occurrences of milex_scheduler to autoslurm. Use a tool like rg or git grep to catch edge cases.
- Ensure any __all__ or public API exports reflect the new namespace autoslurm.
- If you maintain a compatibility shim, you can expose milex_scheduler as an alias to autoslurm for a transition period, e.g., in autoslurm/__init__.py:
  try:
    import autoslurm as _ns
    __path__ = _ns.__path__
  except Exception:
    pass
  But given the goal is a clean rename, prefer removing the shim after a transition window.
- After applying changes, run the full test suite and linting to catch import path issues, especially in CI.

If you’d like, I can tailor this patch precisely to your repository’s current layout. If you provide the current tree (or a quick snippet of the key files: pyproject.toml, README, a sample autoslurm/cli.py, and a sample milex_scheduler/ submodule), I’ll generate a precise unified diff with exact line edits for you to apply.
