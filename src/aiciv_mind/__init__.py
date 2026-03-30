"""
aiciv-mind: Purpose-built AI operating system for AiCIV civilizations.

An architecture designed from first principles for how AI actually thinks,
learns, and scales — not a wrapper around Claude Code but a replacement
for it at the architecture layer.
"""

__version__ = "0.1.0"
__author__ = "A-C-Gee / Corey Cottrell"

from aiciv_mind.manifest import MindManifest, ModelConfig, AuthConfig, MemoryConfig, ToolConfig, SubMindRef
from aiciv_mind.memory import Memory, MemoryStore

__all__ = [
    "MindManifest",
    "ModelConfig",
    "AuthConfig",
    "MemoryConfig",
    "ToolConfig",
    "SubMindRef",
    "Memory",
    "MemoryStore",
]
