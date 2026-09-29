def parse(text: str) -> dict:
    """Parse a small line-oriented key = value configuration."""
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"invalid assignment: {line!r}")
        result[key.strip()] = value.strip()
    return result
