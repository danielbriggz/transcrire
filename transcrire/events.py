# ============================================================
# Transcrire — Internal Event Emitter
# ============================================================
# Lightweight pub/sub system that decouples the pipeline from
# whatever is consuming it.
#
# The pipeline emits events. The CLI registers handlers and
# renders them. The future GUI registers different handlers
# and sends WebSocket messages — no pipeline code changes
# required.
#
# Usage:
#   # Register a handler (in cli/main.py at startup)
#   from transcrire.events import on
#   on("stage_completed", lambda **d: print(d["stage"]))
#
#   # Emit an event (in core/pipeline.py)
#   from transcrire.events import emit
#   emit("stage_completed", stage="FETCH", episode_id=1)
#
# Events emitted by the pipeline:
#   stage_started     — stage, episode_id
#   stage_completed   — stage, episode_id, output_paths, duration_ms
#   stage_failed      — stage, episode_id, error
#   groq_fallback     — episode_id, reason
#   checkpoint_saved  — episode_id, chunk_index, total_chunks
#   pipeline_complete — episode_id, completion_level
# ============================================================

from collections import defaultdict
from typing import Callable

_listeners: dict[str, list[Callable]] = defaultdict(list)


def on(event: str, handler: Callable) -> None:
    """Register a handler for the given event name."""
    _listeners[event].append(handler)


def off(event: str, handler: Callable) -> None:
    """Deregister a handler. Silent no-op if not registered."""
    try:
        _listeners[event].remove(handler)
    except ValueError:
        pass


def emit(event: str, **data) -> None:
    """
    Fire all registered handlers for the given event.
    Handlers are called in registration order.
    Exceptions in handlers are silenced to prevent a bad
    handler from breaking the pipeline.
    """
    for handler in _listeners[event]:
        try:
            handler(**data)
        except Exception:
            pass


def clear() -> None:
    """Remove all registered handlers. Useful in tests."""
    _listeners.clear()
