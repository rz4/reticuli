"""Simple advice about a traced session's readiness to become a claim."""
from __future__ import annotations

import os

from . import authoring, kernel


def advise(workspace):
    try:
        events = authoring._events(workspace)
        commands = [event['cmd'] for event in events if event.get('event') == 'bash' and event.get('cmd')]
        sealable = bool(commands and any(event.get('event') == 'prompt' for event in events))
        return {'sealable': sealable, 'gate': commands[-1] if commands else None,
                'events': len(events)}
    except kernel.ClaimError as error:
        return {'sealable': False, 'reason': str(error), 'gate': None, 'events': 0}
