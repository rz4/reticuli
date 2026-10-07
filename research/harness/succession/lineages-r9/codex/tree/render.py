"""Small presentation helpers and a TOML recipe writer."""
from __future__ import annotations
import datetime
import json


def _value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(_value(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{_key(k)} = {_value(v)}' for k, v in value.items()) + ' }'
    raise TypeError(f'unsupported TOML value: {value!r}')


def _key(key):
    import re
    return key if re.fullmatch(r'[A-Za-z0-9_-]+', key) else json.dumps(key)


def dump_recipe(recipe):
    lines = ['[claim]']
    for key, value in recipe['claim'].items():
        lines.append(f'{_key(key)} = {_value(value)}')
    for step in recipe.get('step', []):
        lines.extend(['', '[[step]]'])
        for key, value in step.items():
            lines.append(f'{_key(key)} = {_value(value)}')
    return '\n'.join(lines) + '\n'


def toml(recipe):
    return dump_recipe(recipe)


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    seconds = float(seconds)
    return f'{seconds:.1f}s' if seconds < 60 else f'{int(seconds // 60)}m {seconds % 60:.0f}s'


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace('Z', '+00:00'))
    delta = datetime.datetime.now(datetime.timezone.utc) - when
    return duration(max(0, delta.total_seconds())) + ' ago'


def table(rows, columns=None):
    rows = list(rows)
    columns = list(columns or (rows[0].keys() if rows else []))
    widths = {c: max(len(str(c)), *(len(str(r.get(c, ''))) for r in rows)) for c in columns}
    line = lambda r: '  '.join(str(r.get(c, '')).ljust(widths[c]) for c in columns)
    return '\n'.join([line(dict(zip(columns, columns))), *(line(r) for r in rows)])


def tree(rows):
    return '\n'.join(str(row) for row in rows)


def paint(value, *args, **kwargs):
    return str(value)
