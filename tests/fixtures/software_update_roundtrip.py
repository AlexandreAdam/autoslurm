"""Real Git fixture: one working copy updated repeatedly without extra code copies."""

import json
import os
from pathlib import Path
import subprocess
import sys
import venv

from autoslurm import update_software, SoftwareUpdateError, save_config, storage

root = Path(sys.argv[1]).resolve()
root.mkdir()
os.environ.update(GIT_CONFIG_GLOBAL=str(root / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1', GIT_ALLOW_PROTOCOL='file')

def git(*args):
    return subprocess.run(['git', *map(str, args)], capture_output=True, text=True, check=True).stdout.strip()

git('config', '--global', 'user.name', 'Offline fixture')
git('config', '--global', 'user.email', 'fixture@example.invalid')
upstream = root / 'upstream.git'
author = root / 'author'
git('init', '--bare', upstream)
git('init', '-b', 'main', author)
git('-C', author, 'remote', 'add', 'origin', upstream)
(author / '.gitignore').write_text('__pycache__/\n*.egg-info/\nbuild/\n')

# Disposable runtime only; a standard-library backend needs no downloads and
# must not see the conflicting package deliberately placed in this venv.
environment = root / 'environment with spaces'
venv.EnvBuilder(with_pip=True).create(environment)
site = environment / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'
(site / 'autoslurm_build_poison.py').write_text('raise RuntimeError("runtime package leaked into build")\n')
python = str(environment / 'bin/python')

backend = '''from pathlib import Path
import importlib.util
import zipfile

def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    assert importlib.util.find_spec("autoslurm_build_poison") is None, "build was not isolated"
    name = "autoslurm_update_fixture"
    info = name + "-0.1.0.dist-info/"
    wheel = Path(wheel_directory) / (name + "-0.1.0-py3-none-any.whl")
    entries = "[console_scripts]\\nscience-fixture = science:main\\n"
    if "science-new-fixture" in Path("pyproject.toml").read_text():
        entries += "science-new-fixture = science:main\\n"
    files = {
        name + ".pth": str(Path.cwd()) + "\\n",
        info + "METADATA": "Metadata-Version: 2.1\\nName: autoslurm-update-fixture\\nVersion: 0.1.0\\nRequires-Dist: must-not-install-fixture>=1\\n",
        info + "WHEEL": "Wheel-Version: 1.0\\nGenerator: offline-fixture\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n",
        info + "entry_points.txt": entries,
    }
    files[info + "RECORD"] = "".join(path + ",,\\n" for path in [*files, info + "RECORD"])
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, text in files.items():
            archive.writestr(path, text)
    return wheel.name
'''

def commit(value):
    (author / 'science.py').write_text(f'def main():\n    print({value!r})\n')
    extra = '\nscience-new-fixture = "science:main"' if value in {'THIRD', 'FOURTH'} else ''
    (author / 'pyproject.toml').write_text('''[build-system]
requires = []
build-backend = "fixture_backend"
backend-path = ["."]
[project]
name = "autoslurm-update-fixture"
version = "0.1.0"
[project.scripts]
science-fixture = "science:main"''' + extra + '\n')
    (author / 'fixture_backend.py').write_text(backend)
    git('-C', author, 'add', 'science.py', 'pyproject.toml', '.gitignore', 'fixture_backend.py')
    git('-C', author, 'commit', '-m', value)
    git('-C', author, 'push', 'origin', 'main')
    return git('-C', author, 'rev-parse', 'HEAD')

first = commit('FIRST')
git('--git-dir', upstream, 'symbolic-ref', 'HEAD', 'refs/heads/main')
software_root = root / 'software with spaces'
software_root.mkdir()
checkout = software_root / 'science'
# Fixture setup creates the pre-existing checkout. Production updates may never clone.
git('clone', upstream, checkout)
tracking = root / 'tracking'
storage.set_storage_root(tracking)
save_config({'default_machine': 'fixture', 'machines': {'fixture': {
    'software_root': str(software_root), 'venv_path': str(environment)}}})
tracking_before = sorted(str(item.relative_to(tracking)) for item in tracking.rglob('*'))

real_run = subprocess.run
def installed_names():
    response = real_run([python, '-I', '-B', '-c',
                         'import importlib.metadata as m, json; print(json.dumps(sorted(d.metadata["Name"] for d in m.distributions())))'],
                        capture_output=True, text=True, check=True)
    return set(json.loads(response.stdout))

original_distributions = installed_names()
commands = []
def record(command, **kwargs):
    commands.append(command)
    assert command[0] != 'git' or not set(command) & {'clone', 'worktree', 'checkout', 'reset', 'stash'}
    if 'pip' in command:
        assert '--no-deps' in command
        assert '--no-build-isolation' not in command and '--no-index' not in command
    if command[0] == 'ssh':
        assert command[-2:] == ['offline-alias', 'python3 -B -']
        command = [sys.executable, '-B', '-']
    return real_run(command, **kwargs)

second = commit('SECOND')
subprocess.run = record
updated = update_software(project='science')
assert (updated['before_commit'], updated['after_commit']) == (first, second)
assert updated['state'] == 'updated'
assert updated['installation']['state'] == 'installed'
assert real_run([str(environment / 'bin/science-fixture')], capture_output=True, text=True, check=True).stdout.strip() == 'SECOND'
# Same commit must still reinstall, restoring entry points that are absent/stale.
(environment / 'bin/science-fixture').unlink()
assert update_software(project='science')['state'] == 'up_to_date'
assert (environment / 'bin/science-fixture').exists()
assert 'SECOND' in (checkout / 'science.py').read_text()
assert list(software_root.iterdir()) == [checkout]
assert tracking_before == sorted(str(item.relative_to(tracking)) for item in tracking.rglob('*'))

# Dirty/untracked files are never hidden/reset and stop before Git fetch/pull.
(checkout / 'notes.txt').write_text('KEEP')
try:
    update_software(project='science')
except SoftwareUpdateError as error:
    assert error.evidence['state'] == 'failed' and error.evidence['stage'] == 'preflight'
else:
    raise AssertionError('Untracked files must block the update.')
assert (checkout / 'notes.txt').read_text() == 'KEEP'
(checkout / 'notes.txt').unlink()

# Exactly the same standard-library payload runs through fake SSH; no installed
# remote AutoSlurm, worker files or copied sources are needed.
subprocess.run = real_run
third = commit('THIRD')
save_config({'default_machine': 'remote', 'machines': {'remote': {
    'software_root': str(software_root), 'ssh_alias': 'offline-alias', 'venv_path': str(environment)}}})
subprocess.run = record
remote = update_software(project='science')
assert remote['state'] == 'updated' and remote['after_commit'] == third
assert 'THIRD' in (checkout / 'science.py').read_text()
assert real_run([str(environment / 'bin/science-new-fixture')], capture_output=True, text=True, check=True).stdout.strip() == 'THIRD'
origin = real_run([python, '-I', '-B', '-c', 'import science; print(science.__file__)'],
                  capture_output=True, text=True, check=True).stdout.strip()
assert Path(origin).resolve() == (checkout / 'science.py').resolve()
assert not (site / 'science.py').exists()  # editable link, not another source copy
assert installed_names() == original_distributions | {'autoslurm-update-fixture'}
assert list(software_root.iterdir()) == [checkout]
assert sum(command[0] == 'ssh' for command in commands) == 1

# A local commit and an upstream commit diverge: a pull must not merge/reset.
subprocess.run = real_run
(checkout / 'local.txt').write_text('KEEP LOCAL COMMIT')
git('-C', checkout, 'add', 'local.txt')
git('-C', checkout, 'commit', '-m', 'local work')
local_head = git('-C', checkout, 'rev-parse', 'HEAD')
commit('FOURTH')
subprocess.run = record
try:
    update_software(project='science')
except SoftwareUpdateError as error:
    assert error.evidence['state'] == 'failed' and error.evidence['after_commit'] == local_head
else:
    raise AssertionError('Diverged history must never be merged or reset.')
assert (checkout / 'local.txt').read_text() == 'KEEP LOCAL COMMIT'
assert list(software_root.iterdir()) == [checkout]
assert not any((software_root / name).exists() for name in ['sources', 'releases', 'repositories', 'release_records'])
print(json.dumps({'before': first, 'after': third, 'checkouts': 1}))
