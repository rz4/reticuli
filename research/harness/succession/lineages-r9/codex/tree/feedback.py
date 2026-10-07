"""Lightweight advice about whether a traced session can be sealed."""
import json
import os

TRACE = '.reticuli/draft.jsonl'


def advise(workspace):
    path = os.path.join(workspace, TRACE)
    events = []
    try:
        with open(path, encoding='utf-8') as source:
            events = [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError):
        pass
    has_gate = any(row.get('event') == 'bash' and row.get('cmd') for row in events)
    return {'sealable': bool(has_gate), 'events': len(events),
            'reason': 'checked session' if has_gate else 'no checked gate'}
