def parse(text: str) -> dict:
    """Parse key = value configuration text into a dictionary.

    Reads one assignment per line. Blank lines are ignored.
    Values are taken as the rest of the line after the '='.
    """
    result = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        result[key] = value
    return result
