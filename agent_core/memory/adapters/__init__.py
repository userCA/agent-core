from agent_core.memory.adapters.inmemory import InMemoryMemoryStore

try:
    from agent_core.memory.adapters.mem0_adapter import Mem0MemoryStore
except ImportError:
    Mem0MemoryStore = None  # type: ignore[assignment]

try:
    from agent_core.memory.adapters.openviking_adapter import OpenVikingMemoryStore
except ImportError:
    OpenVikingMemoryStore = None  # type: ignore[assignment]

__all__ = ["InMemoryMemoryStore", "Mem0MemoryStore", "OpenVikingMemoryStore"]
