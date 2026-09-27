import pytest

from rsm.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "rsm.sqlite")
    s.crea_schema()
    return s
