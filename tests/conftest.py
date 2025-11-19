import pytest
from autoslurm.storage import ensure_storage_dirs, set_storage_root


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path):
    storage_root = tmp_path / "autoslurm_storage"
    set_storage_root(storage_root)
    ensure_storage_dirs()
    yield storage_root
