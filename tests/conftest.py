import pytest
from aiciv_mind.memory import MemoryStore, Memory
from aiciv_mind.tools import ToolRegistry


@pytest.fixture
def memory_store():
    store = MemoryStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def registry():
    return ToolRegistry()
