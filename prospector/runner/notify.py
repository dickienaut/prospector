"""Notifier seam — where the runner's outputs leave the system (spec §10).

The runner DECIDES what to send (a push is pinned to `fold.state_changed`, §10); the Notifier is
only the transport. In M5's skeleton the transport is `NullNotifier` — it records what WOULD be
sent and sends nothing, so the whole push-decision path is exercised offline while the real
SMTP/SES sender is a later slice (build-order step 4). Tests inject the same seam.

CONTRACT (§10): deterministic templating only — a payload is a plain dict folded from state, never
model-generated prose; and the anti-slot-machine cadence lives in the DECISION (the runner), not
here — a Notifier never manufactures a message the runner did not ask for.
"""

from __future__ import annotations

from typing import Protocol


class Notifier(Protocol):
    """The transport contract the runner calls. `push` fires on a state change or a fault
    (same-day); `heartbeat` is the weekly dead-man (build-order step 4 wires the cadence)."""

    def push(self, payload: dict) -> None: ...

    def heartbeat(self, payload: dict) -> None: ...


class NullNotifier:
    """The M5-skeleton transport: record intent, send nothing. `pushes`/`heartbeats` hold what a
    real sender would have delivered — the run-log reads the counts, tests read the content. This
    keeps the push DECISION honest and testable before the sender exists (fault-on-exception still
    'emails' — it records the intended push — so the control flow is proven end to end)."""

    def __init__(self) -> None:
        self.pushes: list[dict] = []
        self.heartbeats: list[dict] = []

    def push(self, payload: dict) -> None:
        self.pushes.append(payload)

    def heartbeat(self, payload: dict) -> None:
        self.heartbeats.append(payload)
