"""Parse simple key = value configuration text."""


def parse(text: str) -> dict:
    """Return assignments with surrounding key and value whitespace removed."""
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result
