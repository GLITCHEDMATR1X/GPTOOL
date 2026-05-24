#!/usr/bin/env python3
"""Validate that quit/close-app controls live inside the ESC menu, not as a play overlay."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    text = MAIN.read_text(encoding="utf-8")

    if 'text="CLOSE APP"' in text:
        fail('retired top-level CLOSE APP overlay text is still present')
    if re.search(r"safety_exit_root\.show\s*\(", text):
        fail('retired safety_exit_root is still shown somewhere')
    if 'self.safety_exit_button = None' not in text:
        fail('retired safety_exit_button should stay disabled/None')
    if 'self.safety_exit_panel = None' not in text or 'self.safety_exit_hint = None' not in text:
        fail('retired safety overlay panel/hint should stay disabled/None')

    menu_quit_match = re.search(
        r"self\.menu_quit_button\s*=\s*DirectButton\((?P<body>.*?)\n\s*\)",
        text,
        flags=re.S,
    )
    if not menu_quit_match:
        fail('menu_quit_button was not created')
    body = menu_quit_match.group('body')
    required = {
        'parent=self.menu_root': 'quit button must be parented to the ESC menu root',
        'text="QUIT APP"': 'quit button must use clear QUIT APP label',
        'command=self.quit_holoverse_from_menu': 'quit button must call the existing quit handler',
    }
    for needle, message in required.items():
        if needle not in body:
            fail(message)

    if '("QUIT APP", "quit_holoverse_from_menu")' not in text:
        fail('System tab must keep the QUIT APP action')
    if 'Close controls live inside this ESC menu' not in text:
        fail('System tab help text should state the close controls are in-menu')

    print('PASS: ESC close overlay contract is clean')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
