def parse(text: str) -> dict:
    """Parse key = value configuration text and return a dictionary.

    Reads lines of the form 'key = value' and returns the resulting dict.
    Empty documents return an empty dictionary.
    """
    result = {}

    if not text:
        return result

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
