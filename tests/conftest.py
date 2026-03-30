import pytest
from aiciv_mind.memory import MemoryStore, Memory


@pytest.fixture
def memory_store():
    store = MemoryStore(":memory:")
    yield store
    store.close()
