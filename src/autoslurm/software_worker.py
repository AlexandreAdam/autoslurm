"""Versioned in-memory worker: installed remote AutoSlurm is never imported."""

from pathlib import Path

# Loaded through stdin in the chosen interpreter. Sources stay in memory; an
# inspection needs no filesystem writes, temp installation or network bootstrap.
_LOADER = '''
import importlib.abc, importlib.util, sys
class SourceLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in SOURCES:
            return importlib.util.spec_from_loader(fullname, self, is_package=fullname in PACKAGES)
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        module.__file__ = '<autoslurm-worker>/' + module.__name__.replace('.', '/') + '.py'
        exec(compile(SOURCES[module.__name__], module.__file__, 'exec'), module.__dict__)
sys.meta_path.insert(0, SourceLoader())
'''


def worker_bootstrap():
    """Ship the shared owners and a private in-memory copy of the verifier tools."""
    import packaging

    directory = Path(__file__).parent
    names = ('machine_paths', 'software_policy', 'software_manifest', 'git_projects', 'record_files',
             'software_sources', 'python_environments', 'release_verification', 'software_releases')
    sources = {'autoslurm_worker': ''}
    packages = ['autoslurm_worker', 'packaging']
    sources.update({'autoslurm_worker.' + name: (directory / (name + '.py')).read_text() for name in names})
    root = Path(packaging.__file__).parent
    for path in root.rglob('*.py'):
        relative = path.relative_to(root).with_suffix('')
        pieces = list(relative.parts)
        if pieces[-1] == '__init__':
            pieces.pop()
            name = '.'.join(['packaging', *pieces])
            packages.append(name)
        else:
            name = '.'.join(['packaging', *pieces])
        sources[name] = path.read_text()
    return 'SOURCES = ' + repr(sources) + '\nPACKAGES = ' + repr(packages) + '\n' + _LOADER


def worker_script(request, action):
    bootstrap = worker_bootstrap()
    return bootstrap + '\n' + '''
import json, sys
from autoslurm_worker.software_releases import operate_release
if sys.version_info < (3, 11):
    raise RuntimeError('Software preparation requires Python 3.11 or newer.')
''' + 'print(json.dumps(operate_release(' + repr(request) + ', ' + repr(action) + ', ' + repr(bootstrap) + ')))\n'


def launcher_script(request, action):
    """System Python only forwards the worker to the explicitly selected Python."""
    script = worker_script(request, action)
    return ('import subprocess, sys\n'
            'result = subprocess.run(' + repr([request['policy']['python'], '-B', '-']) + ', input=' + repr(script)
            + ', text=True, capture_output=True)\n'
            'if result.returncode:\n'
            '    print("Selected Python could not execute the software worker.", file=sys.stderr)\n'
            '    sys.exit(1)\n'
            'sys.stdout.write(result.stdout)\n')
