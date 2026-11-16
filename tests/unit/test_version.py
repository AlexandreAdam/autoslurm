"""Running version identity and packaging configuration use one literal."""

import ast
from pathlib import Path

import pytest
from packaging.version import Version

import autoslurm
from autoslurm.apps import root
from autoslurm.version import __version__


def test_version_is_one_canonical_public_literal_used_by_build_metadata():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    project_root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((project_root / 'pyproject.toml').read_text())
    assert 'version' not in metadata['project']
    assert metadata['project']['dynamic'] == ['version']
    assert metadata['tool']['setuptools']['dynamic']['version'] == {'attr': 'autoslurm.version.__version__'}
    assert not any(item.startswith('setuptools-scm') for item in metadata['build-system']['requires'])
    tree = ast.parse((project_root / 'src/autoslurm/version.py').read_text())
    values = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
    assert values == [__version__] and autoslurm.__version__ == __version__
    assert str(Version(__version__)) == __version__ and Version(__version__).local is None
    assert f'## {__version__} —' in (project_root / 'CHANGELOG.md').read_text()


def test_version_cli_has_no_configuration_storage_or_external_effects(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('Version lookup performed discovery or an external operation')
    monkeypatch.setattr('subprocess.run', forbidden)
    monkeypatch.setattr('builtins.open', forbidden)
    monkeypatch.setattr(Path, 'read_text', forbidden)
    monkeypatch.setattr(Path, 'mkdir', forbidden)
    for action in root.ACTION_HANDLERS:
        monkeypatch.setitem(root.ACTION_HANDLERS, action, forbidden)
    with pytest.raises(SystemExit) as stopped:
        root.main(['--version'])
    assert stopped.value.code == 0
    assert capsys.readouterr() == (f'autoslurm {__version__}\n', '')


def test_application_version_option_is_forwarded_to_selected_command(monkeypatch):
    calls = []
    monkeypatch.setitem(root.ACTION_HANDLERS, 'schedule', lambda args: calls.append(args))
    root.main(['schedule', 'science', '--version'])
    assert calls == [['science', '--version']]


def test_root_help_advertises_version(capsys):
    root.main(['--help'])
    assert '--version' in capsys.readouterr().out
