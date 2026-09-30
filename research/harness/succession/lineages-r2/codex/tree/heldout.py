"""Helpers for separately supplied acceptance criteria.

Held-out criteria are not part of a claim's identity. Their results can be
reported by assessment tools without being mistaken for the claim's gates.
"""

from __future__ import annotations

from . import kernel


def run(directory, command, *, timeout=None):
    """Run a supplied criterion with the kernel's bounded gate environment."""
    parsed = kernel.load_recipe(directory)
    return kernel.run_gate(command, directory, parsed, timeout=timeout)
