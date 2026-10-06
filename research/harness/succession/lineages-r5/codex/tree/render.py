"""Small text renderers, including a deterministic TOML recipe writer."""
import datetime
import json


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(toml(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{key} = {toml(item)}' for key, item in value.items()) + ' }'
    raise TypeError(f'cannot write TOML value {value!r}')


def dump_recipe(recipe):
    lines = ['[claim]']
    lines.extend(f'{key} = {toml(value)}' for key, value in recipe['claim'].items())
    for step in recipe.get('step', []):
        lines.extend(['', '[[step]]'])
        lines.extend(f'{key} = {toml(value)}' for key, value in step.items())
    return '\n'.join(lines) + '\n'


def short(value, length=12):
    return str(value)[:length]


def duration(seconds):
    return f'{seconds:.1f}s'


def ago(when):
    try:
        at = datetime.datetime.fromisoformat(when.replace('Z', '+00:00'))
        return duration((datetime.datetime.now(datetime.timezone.utc) - at).total_seconds()) + ' ago'
    except (ValueError, TypeError):
        return str(when)


def paint(value, *args, **kwargs):
    return str(value)


def table(rows, *args, **kwargs):
    return '\n'.join('  '.join(map(str, row)) for row in rows)


def tree(rows, *args, **kwargs):
    return '\n'.join(map(str, rows))
