"""Small human-facing renderers and a TOML recipe writer."""
from __future__ import annotations

import datetime
import json


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(toml(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{key} = {toml(item)}' for key, item in value.items()) + ' }'
    raise TypeError(f'cannot write TOML value {value!r}')


def dump_recipe(recipe):
    lines = ['[claim]']
    for key, value in recipe['claim'].items():
        lines.append(f'{key} = {toml(value)}')
    for step in recipe.get('step', []):
        lines.extend(('', '[[step]]'))
        for key, value in step.items():
            lines.append(f'{key} = {toml(value)}')
    return '\n'.join(lines) + '\n'


def short(value, width=12):
    return str(value)[:width]


def duration(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return f'{seconds:.1f}s'
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f'{int(minutes)}m {rem:.0f}s'
    hours, minutes = divmod(minutes, 60)
    return f'{int(hours)}h {int(minutes)}m'


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace('Z', '+00:00'))
    now = datetime.datetime.now(datetime.timezone.utc)
    return duration(max(0, (now - when).total_seconds())) + ' ago'


def paint(value, color=None):
    return str(value)


def table(rows, headers=None):
    rows = [list(map(str, row)) for row in rows]
    if headers:
        rows.insert(0, list(map(str, headers)))
    if not rows:
        return ''
    widths = [max(len(row[i]) if i < len(row) else 0 for row in rows) for i in range(max(map(len, rows)))]
    return '\n'.join('  '.join((row[i] if i < len(row) else '').ljust(widths[i]) for i in range(len(widths))).rstrip() for row in rows)


def tree(items, indent=0):
    if isinstance(items, dict):
        return '\n'.join(' ' * indent + str(key) + ('\n' + tree(value, indent + 2) if isinstance(value, (dict, list)) else ': ' + str(value)) for key, value in items.items())
    if isinstance(items, list):
        return '\n'.join(' ' * indent + '- ' + (('\n' + tree(value, indent + 2)) if isinstance(value, (dict, list)) else str(value)) for value in items)
    return ' ' * indent + str(items)
