"""Parse simple line-oriented key/value configuration text."""


def parse(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result
