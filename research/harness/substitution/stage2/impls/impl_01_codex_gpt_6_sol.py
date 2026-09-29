"""Parse a small line-oriented key/value configuration."""


def parse(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result
