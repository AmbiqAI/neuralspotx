"""Opt-in internal handoff; normal operations do not consume this protocol yet."""

from ._reader import ConfiguredDebugContext, ConfiguredDebugTarget, load_debug_context
from ._snapshot import DebugSnapshot, capture_debug_context
