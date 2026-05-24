"""Deprecated compatibility shim for older HoloCore launch paths.

The HoloCore input/menu contract is now implemented directly in ``main.py``.
This module intentionally performs no import-hook or ShowBase monkey-patching;
it remains only so stale wrappers that import ``install`` fail harmlessly.
"""
from __future__ import annotations


def install() -> None:
    print("holocore_menu_input_guard deprecated=1 direct_main_bindings=1")


def uninstall() -> None:
    return None
