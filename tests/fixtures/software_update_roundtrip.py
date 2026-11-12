"""Real Git fixture: one working copy updated repeatedly without extra code copies."""

import json
import os
from pathlib import Path
import subprocess
import sys

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

def commit(value):
    (author / 'science.py').write_text(value)
    git('-C', author, 'add', 'science.py')
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
save_config({'default_machine': 'fixture', 'machines': {'fixture': {'software_root': str(software_root)}}})
tracking_before = sorted(str(item.relative_to(tracking)) for item in tracking.rglob('*'))

real_run = subprocess.run
commands = []
def record(command, **kwargs):
    commands.append(command)
    assert command[0] != 'git' or not set(command) & {'clone', 'worktree', 'checkout', 'reset', 'stash'}
    if command[0] == 'ssh':
        assert command[-2:] == ['offline-alias', 'python3 -B -']
        command = [sys.executable, '-B', '-']
    return real_run(command, **kwargs)

second = commit('SECOND')
subprocess.run = record
updated = update_software(project='science')
assert (updated['before_commit'], updated['after_commit']) == (first, second)
assert updated['state'] == 'updated'
assert update_software(project='science')['state'] == 'up_to_date'
assert (checkout / 'science.py').read_text() == 'SECOND'
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
# remote AutoSlurm, worker files, copied sources or installations are needed.
subprocess.run = real_run
third = commit('THIRD')
save_config({'default_machine': 'remote', 'machines': {'remote': {'software_root': str(software_root), 'ssh_alias': 'offline-alias'}}})
subprocess.run = record
remote = update_software(project='science')
assert remote['state'] == 'updated' and remote['after_commit'] == third
assert (checkout / 'science.py').read_text() == 'THIRD'
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
