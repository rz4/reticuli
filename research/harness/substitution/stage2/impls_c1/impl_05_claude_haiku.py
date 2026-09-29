def parse(text):
    """Parse key=value assignments.

    - One assignment per line (key = value)
    - Numeric values coerce to int
    - Duplicate keys resolve to last assignment
    - Returns a dictionary
    """
    result = {}
    if not text.strip():
        return result

    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Split on '=' (key on left, value on right)
        parts = line.split('=', 1)
        if len(parts) != 2:
            continue

        key = parts[0].strip()
        value = parts[1].strip()

        # Try to coerce to int, otherwise keep as string
        try:
            result[key] = int(value)
        except ValueError:
            result[key] = value

    return result
