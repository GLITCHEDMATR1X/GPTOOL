"""Small render/streaming helper for HoloVerse pass23.

This module is intentionally conservative.  It does not change visuals by
itself; it gives the streaming/dimension code a reusable way to spread work
across frames and avoid spikes when chunks/flora fade in or out.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Iterable


PASS23_MAX_DT = 1.0 / 30.0
PASS23_SLOW_FRAME_DT = 1.0 / 45.0
PASS23_NORMAL_FRAME_DT = 1.0 / 58.0


def clamp_dt(dt: float, max_dt: float = PASS23_MAX_DT) -> float:
    """Clamp a large frame delta so animation does not lurch during hitches."""
    try:
        return max(0.0, min(float(dt), float(max_dt)))
    except Exception:
        return 0.016


@dataclass
class AdaptiveFrameBudget:
    """Adaptive per-frame work limiter.

    Use this around chunk construction/removal or flora placement.  It returns
    fewer operations on slow frames and permits a little more work when the game
    is stable.  This is a low-risk way to smooth frame pacing without changing
    world rules.
    """

    min_ops: int = 1
    normal_ops: int = 2
    max_ops: int = 3
    slow_dt: float = PASS23_SLOW_FRAME_DT
    stable_dt: float = PASS23_NORMAL_FRAME_DT
    smoothing: float = 0.12
    _avg_dt: float = 1.0 / 60.0

    def begin_frame(self, dt: float) -> int:
        dt = clamp_dt(dt)
        self._avg_dt = self._avg_dt * (1.0 - self.smoothing) + dt * self.smoothing
        if self._avg_dt >= self.slow_dt:
            return max(1, int(self.min_ops))
        if self._avg_dt <= self.stable_dt:
            return max(int(self.normal_ops), min(int(self.max_ops), int(self.max_ops)))
        return max(1, int(self.normal_ops))


@dataclass
class WorkQueue:
    """Tiny FIFO work queue for chunk/flora operations."""

    budget: AdaptiveFrameBudget = field(default_factory=AdaptiveFrameBudget)
    _items: Deque[Callable[[], Any]] = field(default_factory=deque)

    def push(self, fn: Callable[[], Any]) -> None:
        self._items.append(fn)

    def extend(self, fns: Iterable[Callable[[], Any]]) -> None:
        for fn in fns:
            self.push(fn)

    def step(self, dt: float) -> int:
        count = self.budget.begin_frame(dt)
        completed = 0
        for _ in range(count):
            if not self._items:
                break
            fn = self._items.popleft()
            fn()
            completed += 1
        return completed

    @property
    def pending(self) -> int:
        return len(self._items)


def safe_detach_batch(nodes: list[Any], limit: int = 4) -> list[Any]:
    """Detach/remove at most ``limit`` nodes and return the leftovers."""
    if not nodes:
        return []
    limit = max(1, int(limit))
    remove_now = nodes[:limit]
    keep = nodes[limit:]
    for node in remove_now:
        try:
            if hasattr(node, "removeNode"):
                node.removeNode()
            elif hasattr(node, "detachNode"):
                node.detachNode()
        except Exception:
            pass
    return keep


def recommended_stream_ops(dt: float) -> int:
    """One-line helper for older code that does not want a budget object."""
    dt = clamp_dt(dt)
    if dt >= PASS23_SLOW_FRAME_DT:
        return 1
    if dt <= PASS23_NORMAL_FRAME_DT:
        return 2
    return 1
