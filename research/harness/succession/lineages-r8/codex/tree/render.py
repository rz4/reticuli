"""Small text renderers for claim authoring."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return '[' + ', '.join(_value(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{key} = {_value(item)}' for key, item in value.items()) + ' }'
    return str(value)


def dump_recipe(recipe):
    lines = ['[claim]']
    lines.extend(f'{key} = {_value(value)}' for key, value in recipe['claim'].items())
    for step in recipe.get('step', []):
        lines.extend(['', '[[step]]'])
        lines.extend(f'{key} = {_value(value)}' for key, value in step.items())
    return '\n'.join(lines) + '\n'


def toml(value):
    return dump_recipe(value) if isinstance(value, dict) and 'claim' in value else _value(value)


def short(value, width=12):
    return str(value)[:width]


def duration(seconds):
    seconds = float(seconds)
    return f'{seconds:.1f}s' if seconds < 60 else f'{int(seconds // 60)}m {seconds % 60:.1f}s'


def ago(when):
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace('Z', '+00:00'))
    if isinstance(when, (int, float)):
        when = datetime.fromtimestamp(when, timezone.utc)
    delta = max(0, int((datetime.now(timezone.utc) - when).total_seconds()))
    if delta < 60:
        return f'{delta}s ago'
    if delta < 3600:
        return f'{delta // 60}m ago'
    if delta < 86400:
        return f'{delta // 3600}h ago'
    return f'{delta // 86400}d ago'


def table(rows, columns=None):
    rows = list(rows)
    columns = list(columns or (rows[0].keys() if rows and isinstance(rows[0], dict) else []))
    if not columns:
        return ''
    cells = [[str(row.get(key, '')) for key in columns] for row in rows]
    widths = [max(len(str(key)), *(len(row[i]) for row in cells)) for i, key in enumerate(columns)]
    head = '  '.join(str(key).ljust(widths[i]) for i, key in enumerate(columns))
    return '\n'.join([head, '  '.join('-' * width for width in widths)] +
                     ['  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in cells])


def tree(rows, indent=0):
    if isinstance(rows, dict):
        return '\n'.join(' ' * indent + str(key) + ('\n' + tree(value, indent + 2) if isinstance(value, (dict, list)) else ': ' + str(value)) for key, value in rows.items())
    if isinstance(rows, list):
        return '\n'.join(' ' * indent + '- ' + (('\n' + tree(value, indent + 2)) if isinstance(value, (dict, list)) else str(value)) for value in rows)
    return ' ' * indent + str(rows)


def paint(value, *_args, **_kwargs):
    return str(value)
