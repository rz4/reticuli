"""Lightweight advice about whether a draft session can form a claim."""
from __future__ import annotations
import os
from . import authoring, kernel


def advise(directory):
    try:
        events = authoring._events(directory)
        gates = [e for e in events if e.get('event') == 'bash' and e.get('cmd')]
        sealable = bool(gates and any(e.get('event') == 'prompt' for e in events))
        return {'sealable': sealable, 'gates': len(gates),
                'reason': 'gate observed' if sealable else 'no checked session'}
    except kernel.ClaimError as exc:
        return {'sealable': False, 'gates': 0, 'reason': str(exc)}
