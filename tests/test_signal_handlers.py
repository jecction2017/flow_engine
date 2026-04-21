from __future__ import annotations

import signal

import pytest

from flow_engine.engine import resources


def test_on_signal_chains_to_previous_sigint_handler() -> None:
    called = {"n": 0}

    def _hook() -> None:
        called["n"] += 1

    dereg = resources.register_cancel(_hook)
    try:
        resources._previous_signal_handlers[signal.SIGINT] = signal.default_int_handler
        with pytest.raises(KeyboardInterrupt):
            resources._on_signal(signal.SIGINT, None)
        assert called["n"] == 1
    finally:
        resources._previous_signal_handlers.pop(signal.SIGINT, None)
        dereg()


def test_on_signal_without_previous_handler_only_cancels() -> None:
    called = {"n": 0}

    def _hook() -> None:
        called["n"] += 1

    dereg = resources.register_cancel(_hook)
    try:
        resources._previous_signal_handlers.pop(signal.SIGINT, None)
        resources._on_signal(signal.SIGINT, None)
        assert called["n"] == 1
    finally:
        dereg()
