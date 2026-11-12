"""Readiness checks the actual declared dependency closure, without imports."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from autoslurm.release_verification import inspect_runtime


class Distribution:
    def __init__(self, name, location, *, version='1', requirements=(), python=None, entries=()):
        self.metadata = {'Name': name, 'Requires-Python': python}
        self.version = version
        self.requires = list(requirements)
        self.entry_points = entries
        self.location = location

    def locate_file(self, value):
        return Path(self.location) / value


def inspect(monkeypatch, tmp_path, *, requirements=(), numpy='2.2', python=None, constraints=(), modules=(), extra=()):
    packages = [Distribution('science', tmp_path, requirements=requirements, python=python), *extra]
    if numpy is not None:
        packages.append(Distribution('numpy', '/base', version=numpy))
    monkeypatch.setattr('importlib.metadata.distributions', lambda: packages)
    return inspect_runtime([{'distribution': 'science', 'version': '1', 'modules': modules}], str(tmp_path), constraints)


def test_compatible_stricter_base_and_target_markers_are_allowed(tmp_path, monkeypatch):
    result = inspect(monkeypatch, tmp_path, requirements=['numpy>=1.26', 'absent; python_version < "1"'])
    assert result['errors'] == []
    assert result['inventory']['numpy']['version'] == '2.2'


@pytest.mark.parametrize('version', ['2.2', None])
def test_missing_and_conflicting_dependencies_block_readiness(tmp_path, monkeypatch, version):
    result = inspect(monkeypatch, tmp_path, requirements=['numpy<2'], numpy=version)
    assert any('dependency numpy' in text for text in result['errors'])


def test_transitive_extra_requirements_are_checked(tmp_path, monkeypatch):
    helper = Distribution('helper', '/base', requirements=['numpy<2; extra == "fast"'])
    result = inspect(monkeypatch, tmp_path, requirements=['helper[fast]'], extra=[helper])
    assert any("helper's requirements" in text for text in result['errors'])


def test_incompatible_python_and_machine_constraints_block_readiness(tmp_path, monkeypatch):
    result = inspect(monkeypatch, tmp_path, python='>999', constraints=['numpy<2'])
    assert any('Python does not satisfy' in text for text in result['errors'])
    assert any('Machine constraint' in text for text in result['errors'])


def test_direct_source_dependencies_require_verification_without_leaking_urls(tmp_path, monkeypatch):
    result = inspect(monkeypatch, tmp_path, requirements=['numpy @ https://token@private.invalid/numpy.whl'])
    assert any('explicit source verification' in text for text in result['errors'])
    assert 'token' not in str(result)


def test_import_from_another_checkout_is_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr('importlib.machinery.PathFinder.find_spec', lambda *a: SimpleNamespace(origin='/old/science.py'))
    result = inspect(monkeypatch, tmp_path, modules=['science'])
    assert any('outside the application release' in text for text in result['errors'])


def test_requested_application_cannot_shadow_python_standard_library(tmp_path, monkeypatch):
    result = inspect(monkeypatch, tmp_path, modules=['sys'])
    assert any('standard library' in text for text in result['errors'])
