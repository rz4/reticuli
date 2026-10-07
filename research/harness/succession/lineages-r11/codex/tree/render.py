"""Small text renderers and a deterministic TOML recipe writer."""
import datetime
import json


def _toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(_toml_value(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{ ' + ', '.join(f'{k} = {_toml_value(v)}' for k, v in value.items()) + ' }'
    raise TypeError(f'cannot write TOML value {value!r}')


def dump_recipe(recipe):
    lines = []
    for section, values in recipe.items():
        if section == 'step':
            continue
        lines.append(f'[{section}]')
        lines.extend(f'{key} = {_toml_value(value)}' for key, value in values.items())
        lines.append('')
    for step in recipe.get('step', []):
        lines.append('[[step]]')
        lines.extend(f'{key} = {_toml_value(value)}' for key, value in step.items())
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def toml(value):
    return dump_recipe(value) if isinstance(value, dict) and 'claim' in value else _toml_value(value)


def short(value, width=12):
    return str(value)[:width]


def duration(seconds):
    return f'{float(seconds):.1f}s'


def ago(when):
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when.replace('Z', '+00:00'))
    if isinstance(when, (int, float)):
        when = datetime.datetime.fromtimestamp(when, datetime.timezone.utc)
    return duration((datetime.datetime.now(datetime.timezone.utc) - when).total_seconds()) + ' ago'


def table(rows, headers=None):
    rows = list(rows)
    if headers is not None:
        rows.insert(0, headers)
    return '\n'.join('  '.join(str(cell) for cell in row) for row in rows)


def tree(value, indent=0):
    if isinstance(value, dict):
        return '\n'.join(' ' * indent + str(k) + (':\n' + tree(v, indent + 2) if isinstance(v, (dict, list)) else ': ' + str(v)) for k, v in value.items())
    if isinstance(value, list):
        return '\n'.join(' ' * indent + '- ' + (tree(v, indent + 2).lstrip() if isinstance(v, (dict, list)) else str(v)) for v in value)
    return ' ' * indent + str(value)


def paint(value, *_args, **_kwargs):
    return str(value)


dump_recipe = dump_recipe
