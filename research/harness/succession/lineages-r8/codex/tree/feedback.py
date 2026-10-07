"""Read a draft session and report whether it can be sealed."""
import json
import os
from .authoring import TRACE


def advise(directory):
    path = os.path.join(directory, TRACE)
    try:
        with open(path, encoding='utf-8') as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    gates = [event['cmd'] for event in events if event.get('event') == 'bash' and isinstance(event.get('cmd'), str)]
    return {'sealable': bool(gates), 'gates': gates, 'events': len(events)}
