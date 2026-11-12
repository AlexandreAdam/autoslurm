"""Build/install application wheels without modifying the scientific dependency base."""

import email.parser
import hashlib
import os
from pathlib import Path
import re
import subprocess
import zipfile


class EnvironmentPreparationError(RuntimeError):
    pass


def run_python(policy, arguments, *, cwd, environment=None, input_text=None):
    result = subprocess.run([policy["python"], "-B", *arguments], cwd=str(cwd),
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", **(environment or {})},
                            input=input_text, capture_output=True, text=True, timeout=300)
    if result.returncode:
        # pip/build backend output can contain URLs/credentials. Preserve stage
        # and exit status, never raw command output in public tracking evidence.
        raise EnvironmentPreparationError(f"Python package operation failed (exit {result.returncode}); check the selected environment and build prerequisites.")
    return result.stdout


def installation_hash(path):
    digest = hashlib.sha256()
    for item in sorted(Path(path).rglob("*")):
        if item.is_symlink():
            raise EnvironmentPreparationError("Installed application contains a redirected path.")
        if item.is_file() and "__pycache__" not in item.parts:
            digest.update(str(item.relative_to(path)).encode() + b"\0")
            digest.update(item.read_bytes())
    return digest.hexdigest()


def build_wheels(projects, directory, policy, progress):
    """Build one fixed-source wheel per requested project with existing build tools."""
    artifacts, names, paths = [], set(), set()
    directory = Path(directory)
    for project in projects:
        progress("building", project["name"])
        output = directory / "wheels" / project["name"]
        output.mkdir(parents=True)
        run_python(policy, ["-m", "pip", "--disable-pip-version-check", "--no-cache-dir", "wheel", "--no-deps", "--no-build-isolation",
                            "--no-index", "--wheel-dir", str(output), project["install_path"]], cwd=directory)
        wheels = list(output.glob("*.whl"))
        if len(wheels) != 1:
            raise EnvironmentPreparationError("Each requested project must build exactly one wheel.")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise EnvironmentPreparationError("Wheel distribution metadata is missing or ambiguous.")
            info = email.parser.Parser().parsestr(archive.read(metadata[0]).decode())
            name = re.sub(r"[-_.]+", "-", info["Name"]).lower()
            if name in names:
                raise EnvironmentPreparationError("Requested projects build conflicting distribution names.")
            names.add(name)
            modules = set()
            contents = {}
            for entry in archive.namelist():
                parts = Path(entry).parts
                if Path(entry).is_absolute() or ".." in parts:
                    raise EnvironmentPreparationError("Wheel contains an unsafe path.")
                if not parts or entry.endswith("/") or ".dist-info" in parts[0]:
                    continue
                if parts[0].endswith(".data"):
                    raise EnvironmentPreparationError("Relocated wheel data/scripts are not supported in managed application releases yet.")
                if entry in paths:
                    raise EnvironmentPreparationError("Requested distributions overwrite the same application file.")
                paths.add(entry)
                contents[entry] = hashlib.sha256(archive.read(entry)).hexdigest()
                top = parts[0].split(".")[0]
                if top.isidentifier() and (len(parts) > 1 or entry.endswith((".py", ".so", ".pyd"))):
                    modules.add(top)
        artifacts.append({**project, "distribution": name, "version": info["Version"],
                          "wheel": str(wheel), "wheel_hash": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                          "modules": sorted(modules), "contents": contents})
    return artifacts


def install_wheels(artifacts, directory, policy):
    target = Path(directory) / "site-packages"
    if target.exists():
        raise EnvironmentPreparationError("Refusing to install over an existing application installation.")
    run_python(policy, ["-m", "pip", "--disable-pip-version-check", "--no-cache-dir", "install", "--no-index", "--no-deps", "--no-compile",
                        "--no-warn-script-location", "--target", str(target), *[item["wheel"] for item in artifacts]], cwd=directory)
    for artifact in artifacts:
        for name, expected in artifact["contents"].items():
            path = target / name
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise EnvironmentPreparationError("Installed code does not match the requested wheel artifact.")
    return target
