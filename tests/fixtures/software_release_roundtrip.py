"""Offline real Git/wheel fixture, executed in a child so all effects stay local."""

import json
import os
from pathlib import Path
import subprocess
import sys
import venv

from autoslurm import (prepare_software, inspect_software_release, save_config, storage,
                       ExecutionContext, attach_software_manifest, save_bundle, preview_bundle, submit_jobs,
                       SoftwarePreparationError)
from autoslurm.software_execution import select_software_release
from autoslurm.software_manifest import normalize_software_manifest
from autoslurm.bundle_preparation import prepare_bundle
from autoslurm.software_worker import worker_bootstrap
from autoslurm.software_releases import operate_release

root = Path(sys.argv[1]).resolve()
root.mkdir(exist_ok=True)
os.environ.update(GIT_CONFIG_GLOBAL=str(root / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                  GIT_ALLOW_PROTOCOL='file', PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='1',
                  PIP_CACHE_DIR=str(root / 'pip-cache'))
remote = root / 'upstream.git'
source = root / 'author'
repository = 'https://offline.invalid/science.git'

def git(*args):
    return subprocess.run(['git', *map(str, args)], check=True, capture_output=True, text=True).stdout.strip()

git('config', '--global', 'user.name', 'Offline fixture')
git('config', '--global', 'user.email', 'fixture@example.invalid')
git('config', '--global', 'url.' + remote.as_uri() + '.insteadOf', repository)
git('init', '--bare', remote)
git('init', '-b', 'main', source)
git('-C', source, 'remote', 'add', 'origin', repository)
(source / 'science').mkdir()
(source / 'science/__init__.py').write_text('')
(source / 'pyproject.toml').write_text('''[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
[project]
name = "offline-science"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["packaging>=23"]
[project.scripts]
science-command = "science.cli:main"
''')

def commit(value):
    (source / 'science/cli.py').write_text(f'def main():\n    print({value!r})\n\nif __name__ == "__main__":\n    main()\n')
    git('-C', source, 'add', '.')
    git('-C', source, 'commit', '-m', value)
    git('-C', source, 'push', 'origin', 'main')
    git('--git-dir', remote, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    return git('-C', source, 'rev-parse', 'HEAD')

first_commit = commit('FIRST')
runtime = root / 'scientific base'
venv.EnvBuilder(system_site_packages=True, with_pip=False).create(runtime)
runtime_python = str(runtime / 'bin/python')
site = Path(subprocess.run([runtime_python, '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                           capture_output=True, text=True, check=True).stdout.strip())
old_checkout = root / 'legacy source'
(old_checkout / 'science').mkdir(parents=True)
(old_checkout / 'science/__init__.py').write_text('')
(old_checkout / 'science/cli.py').write_text('def main():\n    print("BASELINE")\n\nif __name__ == "__main__":\n    main()\n')
(site / 'legacy-science.pth').write_text(str(old_checkout) + '\n')
metadata = site / 'offline_science-0.1.0.dist-info'
metadata.mkdir()
(metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: offline-science\nVersion: 0.1.0\n')
# A target must not import its installed AutoSlurm during worker bootstrap.
(site / 'sitecustomize.py').write_text('''import builtins
original = builtins.__import__
def checked(name, *args, **kwargs):
    if name == 'autoslurm' or name.startswith('autoslurm.'):
        raise ImportError('Installed AutoSlurm must not be used by the portable worker')
    return original(name, *args, **kwargs)
builtins.__import__ = checked
''')
profile = {'software_root': str(root / 'software with spaces'), 'results_root': str(root / 'data'),
           'venv_path': sys.prefix, 'slurm_account': 'offline',
           'software_runtimes': {'default': {'python': runtime_python}}}
Path(profile['results_root']).mkdir()
storage.set_storage_root(root / 'tracking')
save_config({'default_machine': 'fixture', 'machines': {'fixture': profile}})
request = normalize_software_manifest({'projects': [{'name': 'science', 'repository': repository}]})
first = prepare_software(request, machine='fixture')
assert first['state'] == 'ready', first
assert first['projects'][0]['commit'] == first_commit
assert first['request']['policy']['python'] == runtime_python
assert inspect_software_release(first['release_id'], verify=True)['verification']['state'] == 'verified'

# Preparation never replays an existing durable ID, even through the direct worker.
replayed = operate_release(first['request'], 'prepare', worker_bootstrap())
assert replayed == first

context = ExecutionContext('fixture', profile, str(root / 'tracking'), profile['results_root'], profile['results_root'], False, profile['software_root'])
selected = select_software_release(context, first['release_id'])
assert selected.config == context.config and selected.config['venv_path'] == sys.prefix
job = {'name': 'science', 'script': 'science-command', 'slurm': {}, 'script_args': {}}
prepared = prepare_bundle([job], {'science': []}, selected)
script = prepared.jobs[0].script
assert 'pip ' not in script and 'git ' not in script
assert 'site-packages/bin/science-command' in script
assert subprocess.run(['bash'], input=script, capture_output=True, text=True, check=True).stdout.strip() == 'FIRST'
old_script = script
bundle_path = save_bundle(attach_software_manifest({'science': job}, request), 'study')
preview = preview_bundle(bundle_path, machine='fixture', software_release=first['release_id'])
real_submit_run = subprocess.run
submitted_scripts = []
def fake_scheduler(command, **kwargs):
    if command[0] == 'sbatch':
        submitted_scripts.append(Path(command[-1]).read_text())
        return subprocess.CompletedProcess(command, 0, 'Submitted batch job 101\n', '')
    return real_submit_run(command, **kwargs)
subprocess.run = fake_scheduler
receipt = submit_jobs('study', machine='fixture', bundle_path=bundle_path, software_release=first['release_id'])
subprocess.run = real_submit_run
snapshot = json.loads(Path(receipt['bundle_path']).read_text())
assert submitted_scripts == [preview['jobs']['science']['script']]
assert snapshot['science']['_autoslurm_execution']['software_release']['release_id'] == first['release_id']
assert snapshot['science']['_autoslurm_execution']['software_release']['projects'][0]['commit'] == first_commit

second_commit = commit('SECOND')
second = prepare_software(local_project=source, machine='fixture')
assert second['state'] == 'ready'
assert second['projects'][0]['commit'] == second_commit
assert first['installation'] != second['installation']
second_context = select_software_release(context, second['release_id'])
second_job = {**job, 'script': 'python -m science.cli'}
second_script = prepare_bundle([second_job], {'science': []}, second_context).jobs[0].script
assert subprocess.run(['bash'], input=second_script, capture_output=True, text=True, check=True).stdout.strip() == 'SECOND'
assert subprocess.run(['bash'], input=old_script, capture_output=True, text=True, check=True).stdout.strip() == 'FIRST'
assert inspect_software_release(first['release_id'], verify=True)['verification']['state'] == 'verified'

pinned = prepare_software(local_project=source, revision=first_commit, machine='fixture')
assert pinned['projects'][0]['commit'] == first_commit

# Same reported version is not enough: changing installed code invalidates it.
(Path(pinned['installation']) / 'science/cli.py').write_text('print("changed")\n')
assert inspect_software_release(pinned['release_id'], verify=True)['verification']['state'] == 'invalid'

# Full dependency closure stops incompatible releases without updating the base.
project_file = source / 'pyproject.toml'
project_file.write_text(project_file.read_text().replace('packaging>=23', 'packaging<1'))
commit('CONFLICT')
try:
    prepare_software(local_project=source, machine='fixture')
except SoftwarePreparationError as error:
    assert error.evidence['state'] == 'failed'
    assert error.evidence['error']['stage'] == 'verifying'
    assert 'dependency packaging' in error.evidence['error']['message']
else:
    raise AssertionError('Incompatible dependencies must never become ready.')
assert inspect_software_release(first['release_id'], verify=True)['verification']['state'] == 'verified'
assert subprocess.run([runtime_python, '-m', 'science.cli'], capture_output=True, text=True, check=True).stdout.strip() == 'BASELINE'

# Exercise the exact SSH stdin payload with an older/unusable installed
# AutoSlurm. Only the transport is replaced, not the preparation worker.
from autoslurm import software_preparation as preparation
real_run = subprocess.run
ssh_calls = []
def local_ssh(command, **kwargs):
    if command[0] == 'ssh':
        assert command[-2:] == ['offline-alias', 'python3 -B -']
        ssh_calls.append(command)
        command = [sys.executable, '-B', '-']
    return real_run(command, **kwargs)
preparation.subprocess.run = local_ssh
save_config({'default_machine': 'remote-fixture', 'machines': {'remote-fixture': {**profile, 'ssh_alias': 'offline-alias'}}})
remote_release = prepare_software(local_project=source, revision=first_commit, machine='remote-fixture')
assert remote_release['state'] == 'ready'
assert inspect_software_release(remote_release['release_id'], verify=True)['verification']['state'] == 'verified'
assert len(ssh_calls) == 2
print(json.dumps({'first': first['release_id'], 'second': second['release_id'], 'commits': [first_commit, second_commit]}))
