"""Small presentation helpers and a TOML writer for claim recipes."""
from __future__ import annotations
import datetime
import json
from ._kernel.build import _toml_recipe


def dump_recipe(recipe):
    return _toml_recipe(recipe)


def toml(value):
    return dump_recipe(value)


def short(value, width=12):
    value = str(value)
    return value if len(value) <= width else value[:width]


def duration(seconds):
    seconds = float(seconds)
    return f'{seconds:.1f}s'


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace('Z', '+00:00'))
    if isinstance(when, (float, int)):
        when = datetime.datetime.fromtimestamp(when, datetime.timezone.utc)
    return duration((datetime.datetime.now(datetime.timezone.utc) - when).total_seconds()) + ' ago'


def table(rows, columns=None):
    rows = list(rows)
    columns = list(columns or (rows[0].keys() if rows and isinstance(rows[0], dict) else []))
    if not columns:
        return ''
    data = [[str(row.get(key, '')) for key in columns] for row in rows]
    widths = [max(len(str(key)), *(len(row[i]) for row in data)) for i, key in enumerate(columns)]
    return '\n'.join(['  '.join(str(key).ljust(widths[i]) for i, key in enumerate(columns)),
                      '  '.join('-' * width for width in widths),
                      *('  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in data)])


def tree(value, indent=0):
    if isinstance(value, dict):
        return '\n'.join(' ' * indent + str(key) + ': ' + (tree(item, indent + 2) if isinstance(item, (dict, list)) else str(item)) for key, item in value.items())
    if isinstance(value, list):
        return '\n'.join(' ' * indent + '- ' + tree(item, indent + 2) for item in value)
    return str(value)


def paint(value, color=None):
    return str(value)
