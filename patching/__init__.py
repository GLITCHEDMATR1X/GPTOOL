"""GPTOOL AI Patch Gate subsystem.

Drop-in module for safe AI pass review, additive code combine, override staging, and repo patch approval.
"""

__all__ = [
    "pass_combiner",
    "repo_patch_tool",
    "apply_pass_overrides",
    "patch_gate_menu",
    "bridge_patch_adapter",
]
