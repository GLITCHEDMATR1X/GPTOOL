"""GPTOOL Pass 19 Automation Task Director.

This package adds Codex-style local task planning/execution to GPTOOL while
keeping the existing patch gate approval model: dry-run first, explicit apply,
reports every time, and no silent protected-file mutation.
"""
__all__ = ["task_schema", "task_runner", "test_run_director"]
