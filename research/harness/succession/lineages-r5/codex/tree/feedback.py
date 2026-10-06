"""Brief advice from a session trace."""
import json
import os


def advise(workspace):
    path = os.path.join(workspace, '.reticuli', 'draft.jsonl')
    try:
        with open(path, encoding='utf-8') as stream:
            events = [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        events = []
    return {'sealable': any(e.get('event') == 'bash' for e in events),
            'events': len(events)}
