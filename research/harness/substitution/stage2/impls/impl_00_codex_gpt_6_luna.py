def parse(text: str) -> dict:
    """Parse newline-separated key = value assignments."""
    result = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        result[key.strip()] = value.strip()
    return result
